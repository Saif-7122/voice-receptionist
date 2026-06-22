import os
import asyncio
from twilio.rest import Client

async def handle_escalation(caller_context: str, question: str) -> dict:
    def _sync_send():
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_SMS_NUMBER")
        owner_phone = os.getenv("OWNER_PHONE")
        
        if not account_sid or not auth_token or not from_number or not owner_phone:
            return {"notified": False, "channel": "sms", "error": "missing_env"}

        client = Client(account_sid, auth_token)
        
        body = (
            f"Escalation Alert:\n"
            f"Question: {question}\n"
            f"Context: {caller_context}"
        )

        try:
            client.messages.create(
                body=body,
                from_=from_number,
                to=owner_phone
            )
            return {"notified": True, "channel": "sms"}
        except Exception:
            return {"notified": False, "channel": "sms"}

    return await asyncio.to_thread(_sync_send)

async def fire_escalation(call_id: str, business_id: str, unanswered_question: str, transcript_so_far: str) -> dict:
    return await handle_escalation(caller_context=transcript_so_far, question=unanswered_question)

async def fire_booking_confirmation(*args, **kwargs):
    pass

