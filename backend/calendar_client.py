import os
import json
import asyncio
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

async def create_event(patient_name: str, age: str, reason: str, date: str, time: str, doctor_name: str, duration_minutes: int = 30):
    def _sync_create():
        service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        calendar_id = os.getenv("CLINIC_CALENDAR_ID")
        
        if not service_account_json or not calendar_id:
            return "mock_event_id"

        creds = Credentials.from_service_account_info(json.loads(service_account_json))
        service = build("calendar", "v3", credentials=creds)

        try:
            start_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        except Exception:
            start_time = datetime.utcnow() + timedelta(days=1)
            
        end_time = start_time + timedelta(minutes=duration_minutes)

        event_body = {
            "summary": f"Appointment: {patient_name} with {doctor_name}",
            "description": f"Patient: {patient_name}\nAge: {age}\nReason: {reason}",
            "start": {"dateTime": start_time.isoformat() + "Z", "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat() + "Z", "timeZone": "UTC"},
        }

        event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        return event.get("id")

    return await asyncio.to_thread(_sync_create)
