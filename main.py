import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import AsyncGroq

# Load environment variables from .env file
load_dotenv()

# Get environment variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Initialize FastAPI app
app = FastAPI(title="Customer Support Triage API")

# Initialize Groq client
# We initialize it conditionally to handle missing API keys gracefully at startup,
# but it will fail during the API call if missing.
groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

class TicketPayload(BaseModel):
    customer_name: str
    customer_email: str
    message: str

async def classify_ticket(message: str) -> str:
    """
    Sends the message to the Groq API for classification.
    Expects ONLY: "Billing", "Bug", "Feature Request", or "General".
    """
    if not groq_client:
        print("Warning: GROQ_API_KEY not set. Defaulting to 'General'.")
        return "General"

    prompt = (
        "You are an expert customer support triage system.\n"
        "Read the following customer message and classify it into EXACTLY ONE of the following categories:\n"
        "- Billing\n"
        "- Bug\n"
        "- Feature Request\n"
        "- General\n\n"
        "Rules:\n"
        "1. Output ONLY the exact category name.\n"
        "2. Do not include any extra text, punctuation, or explanations.\n\n"
        f"Customer Message: '{message}'"
    )

    try:
        response = await groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.1-8b-instant", # Updated to a supported model
            temperature=0.0, # Zero temperature for deterministic output
            max_tokens=10,
        )
        
        category = response.choices[0].message.content.strip()
        
        # Ensure it's one of the valid categories, otherwise default to General
        valid_categories = ["Billing", "Bug", "Feature Request", "General"]
        if category in valid_categories:
            return category
        else:
            print(f"Unexpected AI output: '{category}'. Defaulting to 'General'.")
            return "General"

    except Exception as e:
        print(f"Error during Groq API call: {e}")
        return "General"


async def notify_slack(ticket: TicketPayload, category: str):
    """
    Helper function to send a JSON payload to Slack Webhook using httpx.
    """
    if not SLACK_WEBHOOK_URL:
        print("Warning: SLACK_WEBHOOK_URL is not set. Cannot send to Slack.")
        return
        
    payload = {
        "text": f"🚨 *New Bug Reported*\n"
                f"*Customer:* {ticket.customer_name} ({ticket.customer_email})\n"
                f"*Message:* {ticket.message}"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(SLACK_WEBHOOK_URL, json=payload)
            response.raise_for_status()
            print("Successfully sent bug report to Slack.")
        except httpx.HTTPError as e:
            print(f"Failed to send to Slack webhook: {e}")


@app.post("/api/ticket")
async def create_ticket(ticket: TicketPayload):
    # 1. Classify the message using AI
    category = await classify_ticket(ticket.message)
    print(f"AI Classification Result: {category}")

    # 2. IF/Switch Branching Logic based on category
    if category == "Bug":
        await notify_slack(ticket, category)
        action_message = "Bug notification sent to Slack."
        
    elif category == "Billing":
        print("Simulating email to Finance Department")
        action_message = "Simulated email to Finance Department."
        
    elif category == "Feature Request" or category == "General":
        print("Simulating email to Shared Inbox")
        action_message = "Simulated email to Shared Inbox."
        
    else:
        # Fallback (should not happen due to validation in classify_ticket)
        print("Simulating email to Shared Inbox")
        action_message = "Simulated email to Shared Inbox."

    return {
        "status": "success",
        "category_assigned": category,
        "action_taken": action_message
    }
