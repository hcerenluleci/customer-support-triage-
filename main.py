import os
import httpx
import datetime
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import service_account
from googleapiclient.discovery import build
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import AsyncGroq

# Load environment variables
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

app = FastAPI(title="Customer Support Triage API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Her yerden gelen isteğe izin ver
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ==========================================
# HW2: GOOGLE SHEETS AYARLARI
# ==========================================
SERVICE_ACCOUNT_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

def save_to_sheets(ticket_data: list):
    """Gelen veriyi Google Sheets'e kaydeder."""
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build("sheets", "v4", credentials=creds)
        body = {"values": [ticket_data]}
        
        try:
            # Önce Türkçe sayfa adıyla dene
            service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range="Sayfa1!A1",
                valueInputOption="RAW",
                body=body
            ).execute()
        except Exception:
            # Hata verirse İngilizce sayfa adıyla dene
            service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range="Sheet1!A1",
                valueInputOption="RAW",
                body=body
            ).execute()

        print("HW2: Veri Google Sheets'e başarıyla eklendi!")
    except Exception as e:
        print(f"HW2 Hatası: Google Sheets'e yazılamadı: {e}")
# ==========================================

class TicketPayload(BaseModel):
    customer_name: str
    customer_email: str
    message: str

async def classify_ticket(message: str) -> str:
    if not groq_client:
        return "General"
    prompt = (
        "You are an expert customer support triage system.\n"
        "Read the following customer message and classify it into EXACTLY ONE: Billing, Bug, Feature Request, or General.\n"
        "Output ONLY the category name.\n"
        f"Customer Message: '{message}'"
    )
    try:
        response = await groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.0,
            max_tokens=10,
        )
        category = response.choices[0].message.content.strip()
        valid_categories = ["Billing", "Bug", "Feature Request", "General"]
        return category if category in valid_categories else "General"
    except:
        return "General"

async def notify_slack(ticket: TicketPayload, category: str):
    if not SLACK_WEBHOOK_URL: return
    payload = {"text": f"🚨 *New Bug Reported*\n*Customer:* {ticket.customer_name}\n*Message:* {ticket.message}"}
    async with httpx.AsyncClient() as client:
        await client.post(SLACK_WEBHOOK_URL, json=payload)

@app.post("/webhook")
async def webhook(ticket: TicketPayload):
    
    category = await classify_ticket(ticket.message)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ticket_row = [
        timestamp, 
        ticket.customer_name, 
        ticket.customer_email, 
        ticket.message, 
        category, 
        "Pending", # Priority
        "Open"     # Status
    ]
    save_to_sheets(ticket_row)

    # 3. Diğer Aksiyonlar (Slack vb.)
    if category == "Bug":
        await notify_slack(ticket, category)
        action_message = "Bug notification sent to Slack."
    else:
        action_message = f"Simulated action for {category}."

    return {
        "status": "success",
        "category_assigned": category,
        "hw2_status": "Saved to Sheets",
        "action_taken": action_message
    }