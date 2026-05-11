import os
import re
import httpx
import smtplib
from email.message import EmailMessage
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import AsyncGroq

try:
    import gspread
except ImportError:
    gspread = None

# Load environment variables from .env file
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

app = FastAPI(title="Customer Support Triage API")

# Initialize Groq client
groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Initialize Google Sheets
try:
    if gspread:
        gc = gspread.service_account(filename=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json"))
        sheet = gc.open(os.getenv("GOOGLE_SHEET_NAME", "Support Tickets")).sheet1
    else:
        sheet = None
except Exception as e:
    print(f"Warning: Could not connect to Google Sheets: {e}")
    sheet = None


class TicketPayload(BaseModel):
    name: Optional[str] = ""
    email: Optional[str] = ""
    message: Optional[str] = ""


def validate_input(ticket: TicketPayload) -> tuple[str, list]:
    errors = []
    if not ticket.name or not ticket.name.strip():
        errors.append("missing name")
    if not ticket.email or not re.match(r"[^@]+@[^@]+\.[^@]+", ticket.email):
        errors.append("invalid email")
    if not ticket.message or not ticket.message.strip():
        errors.append("missing message")
    
    status = "Valid" if not errors else "Invalid"
    return status, errors


async def classify_ticket(message: str) -> tuple[str, str]:
    # Strong rule-based fallback for fraud detection
    message_lower = message.lower()
    fraud_keywords = [
        "fraud", "stolen", "unauthorized", "suspicious", "hacked", 
        "scam", "charged twice", "duplicate charge", "unknown transaction"
    ]
    if any(keyword in message_lower for keyword in fraud_keywords):
        return "fraud", "high"

    # Strong rule-based fallback for technical issues
    tech_keywords = [
        "crash", "crashes", "error", "bug", "login problem", 
        "cannot login", "app not working", "server error", "technical issue"
    ]
    if any(keyword in message_lower for keyword in tech_keywords):
        return "technical", "high"

    if not groq_client:
        print("Warning: GROQ_API_KEY not set. Defaulting to 'general'.")
        return "general", "low"

    prompt = (
        "Classify the following customer support message.\n"
        "Categories: billing, fraud, loan, card_issue, technical, general\n"
        "Priorities: low, medium, high\n"
        "Output ONLY in this exact format:\n"
        "category: <category>\n"
        "priority: <priority>\n\n"
        f"Message: '{message}'"
    )
    try:
        response = await groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.1-8b-instant",
            temperature=0.0,
            max_tokens=50,
        )
        
        content = response.choices[0].message.content.lower()
        
        category = "general"
        priority = "low"
        
        cat_match = re.search(r"category:\s*(billing|fraud|loan|card_issue|technical|general)", content)
        if cat_match:
            category = cat_match.group(1)
            
        pri_match = re.search(r"priority:\s*(low|medium|high)", content)
        if pri_match:
            priority = pri_match.group(1)

        return category, priority

    except Exception as e:
        print(f"Error during Groq API call: {e}")
        return "general", "low"


def route_ticket(category: str) -> str:
    routes = {
        "fraud": "fraud/security team",
        "billing": "finance team",
        "loan": "loan department",
        "card_issue": "card support",
        "technical": "technical support",
        "general": "shared inbox"
    }
    return routes.get(category, "shared inbox")


async def notify_slack(ticket: TicketPayload, category: str) -> bool:
    """
    Helper function to send a JSON payload to Slack Webhook using httpx.
    """
    if not SLACK_WEBHOOK_URL:
        print("Warning: SLACK_WEBHOOK_URL is not set. Cannot send to Slack.")
        return False
        
    payload = {
        "text": f"🚨 *New Technical Issue Reported*\n"
                f"*Customer:* {ticket.name} ({ticket.email})\n"
                f"*Message:* {ticket.message}"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(SLACK_WEBHOOK_URL, json=payload)
            response.raise_for_status()
            print("Successfully sent technical report to Slack.")
            return True
        except Exception as e:
            print(f"Failed to send to Slack webhook: {e}")
            return False


def send_email(ticket: TicketPayload, category: str) -> bool:
    """
    Helper function to send an email using SMTP.
    """
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL")

    if not all([smtp_server, smtp_username, smtp_password, from_email]):
        print("Warning: Missing SMTP configuration. Cannot send email.")
        return False

    if category == "billing":
        to_email = os.getenv("FINANCE_EMAIL")
    elif category == "fraud":
        to_email = os.getenv("FRAUD_EMAIL")
    elif category == "loan":
        to_email = os.getenv("LOAN_EMAIL")
    elif category == "card_issue":
        to_email = os.getenv("CARD_EMAIL")
    else:
        to_email = os.getenv("SHARED_INBOX_EMAIL")

    if not to_email:
        print(f"Warning: No recipient email configured for category '{category}'.")
        return False

    msg = EmailMessage()
    msg.set_content(f"Customer Name: {ticket.name}\nEmail: {ticket.email}\n\nMessage:\n{ticket.message}")
    msg["Subject"] = f"New {category.replace('_', ' ').title()} Ticket"
    msg["From"] = from_email
    msg["To"] = to_email

    try:
        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        print(f"Successfully sent email to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False


@app.post("/api/ticket")
async def create_ticket(ticket: TicketPayload):
    # 1. Validation
    validation_status, validation_errors = validate_input(ticket)
    
    # 2. AI Classification & Routing & Delivery
    if validation_status == "Valid":
        category, priority = await classify_ticket(ticket.message)
        route = route_ticket(category)
        
        # 3. IF/Switch Branching Logic based on category (HW1/HW2 logic preserved)
        if category == "technical":
            success = await notify_slack(ticket, category)
            delivery_status = "success" if success else "failed"
            action_message = "Notification sent to Slack." if success else "Failed to send Slack notification."
        else:
            success = send_email(ticket, category)
            delivery_status = "success" if success else "failed"
            action_message = f"Email sent to {route}." if success else f"Failed to send email to {route}."
    else:
        category, priority, route, delivery_status = "none", "none", "none", "none"
        action_message = "Ticket invalid. Saved as Invalid."

    # 4. Save metadata to Google Sheets
    timestamp = datetime.now().isoformat()
    record = [
        timestamp,
        ticket.name,
        ticket.email,
        ticket.message,
        validation_status,
        ", ".join(validation_errors),
        category,
        priority,
        route,
        delivery_status
    ]
    
    if sheet:
        try:
            # Sync gspread call inside async function (keep it simple as requested)
            sheet.append_row(record)
        except Exception as e:
            print(f"Failed to save to Google Sheets: {e}")
    else:
        print("Google Sheets not configured, record not saved.")

    return {
        "status": "success",
        "validation_status": validation_status,
        "validation_errors": validation_errors,
        "category_assigned": category,
        "priority_assigned": priority,
        "route": route,
        "delivery_status": delivery_status,
        "action_taken": action_message
    }