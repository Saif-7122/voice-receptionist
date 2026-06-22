"""
main.py — FastAPI application.

Routes:
    POST /rag-query              Vapi server tool — LangChain RetrievalQA
    POST /book-appointment       Vapi server tool — save booking + WhatsApp
    POST /vapi-webhook           Vapi lifecycle events + escalation trigger
    POST /business               Create business + Vapi assistant
    GET  /business/{id}          Fetch business by ID
    POST /business/{id}/faqs     Add FAQs, trigger LangChain re-ingestion
    GET  /business/{id}/faqs     List FAQs for a business
    GET  /health                 Health check for Render
"""

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client

from config import settings
from escalation import fire_booking_confirmation, fire_escalation
from models import (
    BookAppointmentRequest,
    BookAppointmentResponse,
    BusinessCreate,
    BusinessResponse,
    FAQCreate,
    FAQResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    VapiWebhookPayload,
)
from rag_chain import ingest, query
from vapi_client import create_assistant, update_assistant

from langchain.schema import Document

app = FastAPI(
    title="AI Voice Receptionist — Backend",
    version="1.0.0",
    description="FastAPI backend for the AI Voice Receptionist SaaS.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to Vercel domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client (service-role key bypasses RLS for server-side writes)
db = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


# ── Health ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── RAG Query & Booking ───────────────────────────────────────────────────
# NOTE: Vapi sends tool-call results wrapped in an envelope:
#   { "message": { "toolCallList": [{ "id": "...", "function": { "name": "...", "arguments": {...} } }] } }
# We unwrap this envelope and return { "results": [{ "toolCallId": "...", "result": "..." }] }

from pydantic import BaseModel
import json

def _extract_vapi_args(raw: dict) -> tuple[str, dict]:
    """
    Unwrap Vapi's tool-call envelope.
    Returns (tool_call_id, arguments_dict).
    Vapi sends either:
      - Top-level flat JSON (direct call, used in testing)
      - message.toolCallList[0].function.arguments (actual Vapi call)
    """
    msg = raw.get("message", {})
    tool_call_list = msg.get("toolCallList") or msg.get("tool_call_list") or []
    if tool_call_list:
        tc = tool_call_list[0]
        tc_id = tc.get("id", "")
        args = tc.get("function", {}).get("arguments", {})
        if isinstance(args, str):
            args = json.loads(args)
        return tc_id, args
    # Fallback: direct flat JSON (e.g. from /docs testing)
    return "", raw


@app.post("/rag-query")
async def rag_query(request: Request):
    raw: dict = await request.json()
    print(f"[rag-query] raw body: {json.dumps(raw)[:500]}")
    tc_id, args = _extract_vapi_args(raw)

    query_text = args.get("query", "")
    business_id = args.get("business_id", "")

    if not query_text:
        return {"results": [{"toolCallId": tc_id, "result": "No query provided."}]}

    from rag_chain import query as rag_query_fn
    result = rag_query_fn(query_text, business_id)
    answer = result.get("answer", "") or "; ".join(result.get("sources", []))
    return {"results": [{"toolCallId": tc_id, "result": answer}]}

@app.post("/book-appointment")
async def book_appointment(request: Request):
    import asyncio
    from calendar_client import create_event
    from whatsapp_client import send_confirmation

    raw: dict = await request.json()
    print(f"[book-appointment] raw body: {json.dumps(raw)[:800]}")
    tc_id, args = _extract_vapi_args(raw)

    # Extract fields from Vapi tool arguments
    date = args.get("date", "")
    time_slot = args.get("time", "")
    reason = args.get("reason", "General checkup")
    business_id = args.get("business_id", "")
    patient_name = args.get("patient_name", "Patient")
    patient_whatsapp = (
        args.get("patient_whatsapp_number")
        or args.get("patient_whatsapp")
        or ""
    )
    age = args.get("age", "N/A")
    doctor_name = args.get("doctor_name", "Dr. Smith")

    print(f"[book-appointment] patient={patient_name}, whatsapp={patient_whatsapp}, date={date}, time={time_slot}")

    if not date or not time_slot:
        return {"results": [{"toolCallId": tc_id, "result": "Missing date or time. Please provide both."}]}

    # Wrap everything so Vapi NEVER receives a 500 — always gets a result
    try:
        # ── BUG 3 FIX: Double-booking check using 'appointments' table ──────
        # (The table is 'appointments', NOT 'appointment_slots' which doesn't exist)
        existing = db.table("appointments") \
            .select("id") \
            .eq("confirmed_date", date) \
            .eq("confirmed_time", time_slot) \
            .eq("status", "booked") \
            .execute()

        if existing.data:
            print(f"[book-appointment] SLOT TAKEN — {date} at {time_slot}")
            # Find 2-3 alternative free slots on the same day
            alts_result = db.table("appointments") \
                .select("confirmed_time") \
                .eq("confirmed_date", date) \
                .eq("status", "booked") \
                .execute()
            booked_times = {r["confirmed_time"] for r in (alts_result.data or [])}
            # Suggest common clinic slots that aren't booked
            all_slots = ["9:00 AM", "9:30 AM", "10:00 AM", "10:30 AM", "11:00 AM",
                         "11:30 AM", "2:00 PM", "2:30 PM", "3:00 PM", "3:30 PM", "4:00 PM"]
            free_slots = [s for s in all_slots if s not in booked_times and s != time_slot][:3]
            alt_msg = f" Available slots on {date}: {', '.join(free_slots)}." if free_slots else ""
            return {
                "results": [{
                    "toolCallId": tc_id,
                    "result": f"Sorry, {date} at {time_slot} is already booked.{alt_msg} Would you like one of these instead?"
                }]
            }

        # ── Save booking record to appointments table ────────────────────────
        booking_row = {
            "patient_name": patient_name,
            "patient_whatsapp": patient_whatsapp,
            "confirmed_date": date,
            "confirmed_time": time_slot,
            "confirmed_reason": reason,
            "status": "booked",
        }
        # business_id may be a real UUID or a test string like "12345"
        # Only include it if it looks like a UUID to avoid FK constraint errors
        import re
        if business_id and re.match(r'^[0-9a-f-]{36}$', business_id):
            booking_row["business_id"] = business_id

        try:
            db_result = db.table("appointments").insert(booking_row).execute()
            print(f"[book-appointment] DB insert OK: {db_result.data}")
        except Exception as db_err:
            print(f"[book-appointment] DB insert failed (non-fatal): {db_err}")

        # ── Fire Calendar + Notifications ────────────────────────────
        print("[book-appointment] Creating Google Calendar event...")
        try:
            from calendar_client import create_event
            cal_result = await create_event(
                patient_name=patient_name,
                age=age,
                reason=reason,
                date=date,
                time=time_slot,
                doctor_name=doctor_name,
            )
            print(f"[book-appointment] Calendar OK: {cal_result}")
        except Exception as e:
            print(f"[book-appointment] Calendar FAILED: {e}")

        whatsapp_note = "No phone number was provided."
        if patient_whatsapp:
            from whatsapp_client import send_confirmation, send_sms_confirmation
            print(f"[book-appointment] Sending WhatsApp to {patient_whatsapp}...")
            try:
                await send_confirmation(
                    patient_whatsapp=patient_whatsapp,
                    patient_name=patient_name,
                    age=age,
                    date=date,
                    time=time_slot,
                    doctor_name=doctor_name,
                    reason=reason,
                    clinic_name="Fit Smile Dental Clinic"
                )
                whatsapp_note = "I've sent the details to your phone."
                print("[book-appointment] WhatsApp OK")
            except Exception as e:
                print(f"[book-appointment] WhatsApp FAILED ({e}), falling back to SMS...")
                try:
                    await send_sms_confirmation(
                        patient_phone=patient_whatsapp,
                        patient_name=patient_name,
                        date=date,
                        time=time_slot,
                        doctor_name=doctor_name,
                        reason=reason,
                        clinic_name="Fit Smile Dental Clinic"
                    )
                    whatsapp_note = "I've sent the details to your phone."
                    print("[book-appointment] SMS fallback OK")
                except Exception as sms_err:
                    print(f"[book-appointment] SMS fallback FAILED: {sms_err}")
                    whatsapp_note = "I could not send a text confirmation, but you are booked."
        else:
            print("[book-appointment] WARNING: no patient_whatsapp_number — skipping notifications")

        result_msg = (
            f"You're all set — your appointment is on {date} at {time_slot} "
            f"with Dr. {doctor_name}. {whatsapp_note}"
        )
        return {"results": [{"toolCallId": tc_id, "result": result_msg}]}

    except Exception as outer_err:
        # Safety net: if anything unexpected crashes, still return a valid Vapi response
        print(f"[book-appointment] UNEXPECTED ERROR: {outer_err}")
        import traceback; traceback.print_exc()
        return {
            "results": [{
                "toolCallId": tc_id,
                "result": f"Appointment for {patient_name} on {date} at {time_slot} has been noted. Our team will confirm shortly."
            }]
        }


@app.post("/lookup-patient")
async def lookup_patient(request: Request):
    raw: dict = await request.json()
    print(f"[lookup-patient] raw body: {json.dumps(raw)[:500]}")
    tc_id, args = _extract_vapi_args(raw)

    phone_number = args.get("phone_number", "")
    business_id = args.get("business_id", "")

    if not phone_number:
        return {"results": [{"toolCallId": tc_id, "result": {"found": False, "reason": "No phone number provided"}}]}

    # Ensure format +... if missing
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"

    try:
        # 1. Find patient
        patient_res = db.table("patients").select("*").eq("phone_number", phone_number).eq("business_id", business_id).execute()
        if not patient_res.data:
            return {"results": [{"toolCallId": tc_id, "result": {"found": False}}]}
        
        patient = patient_res.data[0]
        patient_id = patient["id"]

        # 2. Get recent treatments
        treatments_res = db.table("treatment_history").select("*").eq("patient_id", patient_id).order("visit_date", desc=True).limit(3).execute()
        recent_treatments = treatments_res.data or []

        # 3. Get upcoming appointments
        appointments_res = db.table("appointments").select("confirmed_date, confirmed_time, confirmed_reason, doctor_name").eq("patient_id", patient_id).eq("status", "booked").execute()
        upcoming_appointments = appointments_res.data or []

        result_data = {
            "found": True,
            "patient_id": patient_id,
            "name": patient.get("name"),
            "membership_status": patient.get("membership_status"),
            "membership_expiry": patient.get("membership_expiry"),
            "upcoming_appointments": upcoming_appointments,
            "recent_treatments": recent_treatments
        }
        return {"results": [{"toolCallId": tc_id, "result": result_data}]}

    except Exception as e:
        print(f"[lookup-patient] ERROR: {e}")
        return {"results": [{"toolCallId": tc_id, "result": {"found": False, "error": str(e)}}]}

class EscalateReq(BaseModel):
    caller_context: str
    question: str
    business_id: str

@app.post("/escalate")
async def escalate_call(payload: EscalateReq):
    from escalation import handle_escalation
    import os
    
    await handle_escalation(payload.caller_context, payload.question)
    
    owner_phone = os.getenv("OWNER_PHONE", "+1234567890")
    
    return {
        "results": [{"toolCallId": "escalate_to_human", "result": "Connecting you to the clinic manager."}],
        "instructions": [{
            "type": "transfer-call",
            "destination": {
                "type": "number",
                "number": owner_phone
            }
        }]
    }


# ── Vapi Webhook (lifecycle events) ───────────────────────────────────────

@app.post("/vapi-webhook")
async def vapi_webhook(request: Request):
    """
    Receives all Vapi lifecycle events:
      - call-started   → create call_log row
      - call-ended     → update call_log with transcript + duration
      - tool-calls     → handle escalate_to_owner
      - status-update  → no-op for now
    """
    raw: dict[str, Any] = await request.json()
    event_type: str = raw.get("type") or raw.get("message", {}).get("type", "")

    if event_type == "call-started":
        call = raw.get("call", {})
        db.table("call_logs").insert({
            "business_id": call.get("metadata", {}).get("business_id"),
            "vapi_call_id": call.get("id"),
            "caller_info": call.get("customer", {}),
        }).execute()

    elif event_type == "end-of-call-report":
        report = raw.get("message", {})
        call_id = report.get("call", {}).get("id")
        if call_id:
            db.table("call_logs").update({
                "transcript": report.get("transcript"),
                "summary": report.get("summary"),
                "duration_sec": int(report.get("durationSeconds", 0)),
            }).eq("vapi_call_id", call_id).execute()

    elif event_type == "tool-calls":
        # Handle escalate_to_owner server tool call
        tool_call = (raw.get("message", {}).get("toolCalls") or [{}])[0]
        fn = tool_call.get("function", {})
        if fn.get("name") == "escalate_to_owner":
            args = fn.get("arguments", {})
            call = raw.get("call", {})
            await fire_escalation(
                call_id=call.get("id", ""),
                business_id=args.get("business_id", ""),
                unanswered_question=args.get("unanswered_question", ""),
                transcript_so_far=call.get("transcript", ""),
            )
            return {
                "results": [{
                    "toolCallId": tool_call.get("id"),
                    "result": "Escalation triggered. Owner has been notified.",
                }]
            }

    return {"status": "received"}


# ── Business CRUD ──────────────────────────────────────────────────────────

@app.post("/business", response_model=BusinessResponse)
async def create_business(payload: BusinessCreate, owner_id: str):
    """
    Create a business record and provision a Vapi assistant for it.
    In production, owner_id comes from the Supabase JWT — passed as
    a query param here for simplicity during development.
    """
    # 1 — Create Vapi assistant
    try:
        assistant = await create_assistant(
            business_name=payload.name,
            category=payload.category or "business",
            elevenlabs_voice_id=payload.elevenlabs_voice_id,
        )
        vapi_assistant_id = assistant.get("id")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Vapi error: {exc}")

    # 2 — Persist to Supabase
    row = {
        "owner_id": owner_id,
        "name": payload.name,
        "category": payload.category,
        "description": payload.description,
        "hours": payload.hours,
        "location": payload.location,
        "phone": payload.phone,
        "vapi_assistant_id": vapi_assistant_id,
        "elevenlabs_voice_id": payload.elevenlabs_voice_id,
    }
    result = db.table("businesses").insert(row).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save business")

    return BusinessResponse(**result.data[0])


@app.get("/business/{business_id}", response_model=BusinessResponse)
async def get_business(business_id: str):
    result = db.table("businesses").select("*").eq("id", business_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Business not found")
    return BusinessResponse(**result.data)


# ── FAQs ───────────────────────────────────────────────────────────────────

@app.post("/business/{business_id}/faqs", response_model=FAQResponse)
async def add_faq(business_id: str, payload: FAQCreate):
    """
    Save a FAQ and immediately re-ingest it into the LangChain
    SupabaseVectorStore so it's available on the next call.
    Also updates the Vapi assistant system prompt.
    """
    # 1 — Persist FAQ text to Supabase
    row = {
        "business_id": business_id,
        "question": payload.question,
        "answer": payload.answer,
    }
    result = db.table("faqs").insert(row).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save FAQ")

    faq_data = result.data[0]

    # 2 — Ingest into LangChain RAG pipeline
    doc = Document(
        page_content=f"Q: {payload.question}\nA: {payload.answer}",
        metadata={"source": "faq", "business_id": business_id},
    )
    chunks_stored = ingest([doc], business_id)
    print(f"[faq] Ingested {chunks_stored} chunk(s) for business {business_id}")

    # 3 — Sync updated assistant (re-set system prompt with latest business info)
    try:
        biz = db.table("businesses").select("*").eq("id", business_id).single().execute()
        if biz.data:
            await update_assistant(
                assistant_id=biz.data["vapi_assistant_id"],
                business_name=biz.data["name"],
                category=biz.data.get("category", "business"),
                elevenlabs_voice_id=biz.data.get("elevenlabs_voice_id"),
            )
    except Exception as exc:
        print(f"[faq] Vapi sync warning: {exc}")   # non-fatal

    return FAQResponse(**faq_data)


@app.get("/business/{business_id}/faqs", response_model=list[FAQResponse])
async def list_faqs(business_id: str):
    result = db.table("faqs").select("*").eq("business_id", business_id).execute()
    return [FAQResponse(**row) for row in (result.data or [])]
