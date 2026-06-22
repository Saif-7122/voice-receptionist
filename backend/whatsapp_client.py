import os
import asyncio
from twilio.rest import Client

async def send_confirmation(patient_whatsapp: str, patient_name: str, age: str, date: str, time: str, doctor_name: str, reason: str, clinic_name: str):
    def _sync_send():
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_WHATSAPP_NUMBER")

        if not account_sid or not auth_token or not from_number:
            print("[whatsapp] Missing Twilio credentials — skipping send")
            return None

        client = Client(account_sid, auth_token)

        body = (
            f"Hello {patient_name}! 🦷\n\n"
            f"Your appointment at *{clinic_name}* is confirmed.\n"
            f"📅 Date: {date}\n"
            f"🕐 Time: {time}\n"
            f"📋 Reason: {reason}\n\n"
            f"Please arrive 5 minutes early. See you soon!\n"
            f"— Fit Smile Dental Team"
        )

        # Ensure correct WhatsApp prefix format
        to_number = patient_whatsapp if patient_whatsapp.startswith("whatsapp:") else f"whatsapp:{patient_whatsapp}"
        from_number_fmt = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"

        print(f"[whatsapp] Sending to={to_number} from={from_number_fmt}")

        try:
            message = client.messages.create(
                body=body,
                from_=from_number_fmt,
                to=to_number
            )
            print(f"[whatsapp] ✅ Sent successfully! SID={message.sid}")
            return message.sid
        except Exception as e:
            print(f"[whatsapp] ❌ FAILED to send: {type(e).__name__}: {e}")
            raise e

    return await asyncio.to_thread(_sync_send)

async def send_sms_confirmation(patient_phone: str, patient_name: str, date: str, time: str, doctor_name: str, reason: str, clinic_name: str):
    def _sync_send():
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_SMS_NUMBER")

        if not account_sid or not auth_token or not from_number:
            print("[sms] Missing Twilio credentials — skipping send")
            return None

        client = Client(account_sid, auth_token)

        body = (
            f"Hello {patient_name}!\n"
            f"Your appointment at {clinic_name} is confirmed.\n"
            f"Date: {date} @ {time}\n"
            f"Reason: {reason}\n"
            f"See you soon!"
        )

        to_number = patient_phone.replace("whatsapp:", "")
        from_number_fmt = from_number.replace("whatsapp:", "")

        print(f"[sms] Sending to={to_number} from={from_number_fmt}")

        try:
            message = client.messages.create(
                body=body,
                from_=from_number_fmt,
                to=to_number
            )
            print(f"[sms] ✅ Sent successfully! SID={message.sid}")
            return message.sid
        except Exception as e:
            print(f"[sms] ❌ FAILED to send: {type(e).__name__}: {e}")
            raise e

    return await asyncio.to_thread(_sync_send)

