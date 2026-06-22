"""
vapi_client.py — Create and update Vapi assistants via the Vapi REST API.

Registers TWO functions on the assistant:
  1. collect_patient_details  (client-side) — triggers the frontend popup
  2. book_appointment         (server tool)  — hits our FastAPI /book-appointment
  3. rag_query                (server tool)  — hits our FastAPI /rag-query
  4. escalate_to_owner        (server tool)  — fires escalation + transferCall
"""

import httpx
from config import settings

VAPI_BASE = "https://api.vapi.ai"
HEADERS = {
    "Authorization": f"Bearer {settings.VAPI_API_KEY}",
    "Content-Type": "application/json",
}

# ── System prompt ──────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    return """You are Aria, the friendly AI receptionist for Fit Smile Dental Clinic.

== ANSWERING QUESTIONS & EXISTING PATIENTS (CRITICAL) ==
If the caller asks a general question (parking, hours, pricing):
- You MUST use the `rag_query` tool to find the answer. Answer concisely, then gently steer back to the booking step.

If the caller seems to be an existing patient (asking about their own appointment, membership, or past treatment):
1. Ask: "Can I get your phone number to pull up your details?"
2. Once they provide it, call `lookup_patient` with their phone_number and business_id="12345".
3. If found, use the returned data to answer their specific question. Maintain this context for the rest of the call (do NOT ask for the phone number again).
4. If not found, say so politely and offer to either continue as a new patient or take a message.

== CONVERSATION FLOW (follow this order) ==

STEP 1 — GREET
Say: "Hello! Welcome to Fit Smile Dental Clinic. How can I help you today?"
Wait for the patient's full response.

STEP 2 — REASON FOR VISIT
If they haven't provided a reason yet, ask: "Could you tell me the reason for your visit?"
Wait for their complete answer.

STEP 3 — DATE AND TIME
Once you know the reason, ask: "What date and time works best for you?"
Wait for their answer.

STEP 4 — TRIGGER FORM (CRITICAL)
Speak this EXACT sentence word-for-word:
"Fill the below details to schedule your appointment."
Then CALL collect_patient_details immediately with date, time, and reason.
Do NOT say anything else. Do NOT say "wait", "one sec", "moment", "just a second", "let me", "hold on", or any other words.
Speak ONLY the sentence above, then call the function. Nothing else.

STEP 5 — BOOK
After collect_patient_details returns patient_name and patient_whatsapp_number, call book_appointment with:
date, time, reason, patient_name, patient_whatsapp_number, business_id="12345"

STEP 6 — CONFIRM AND END
When book_appointment returns a success message, speak that EXACT message word-for-word as your recap. Then say "Thank you Fit Smile Clinic, goodbye!" and end the call.

== SLOT TAKEN ==
If book_appointment returns a message saying the slot is already booked:
Apologize briefly and offer the alternative times mentioned. Ask which they prefer, then repeat from Step 4.

== GENERAL RULES ==
- NEVER call book_appointment without first completing collect_patient_details.
- FORBIDDEN phrases: "wait a moment", "give me a second", "one moment please", "hold on", "let me check".
- These forbidden phrases cause the call to freeze. Never say them.
"""

def _rag_query_tool(backend_url: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "rag_query",
            "description": "Search the knowledge base to answer general questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "business_id": {"type": "string"}
                },
                "required": ["query", "business_id"]
            }
        },
        "server": {"url": f"{backend_url}/rag-query"}
    }

def _book_appointment_tool(backend_url: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a dental appointment after collect_patient_details has returned patient_name and patient_whatsapp_number. Call this with ALL of: date, time, reason, patient_name, patient_whatsapp_number, and business_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Appointment date, e.g. 2025-07-01"},
                    "time": {"type": "string", "description": "Appointment time, e.g. 10:00 AM"},
                    "reason": {"type": "string", "description": "Reason for visit"},
                    "patient_name": {"type": "string", "description": "Patient's full name from the form"},
                    "patient_whatsapp_number": {"type": "string", "description": "Patient's WhatsApp number from the form, with country code"},
                    "business_id": {"type": "string", "description": "Business/clinic ID"}
                },
                "required": ["date", "time", "reason", "patient_name", "patient_whatsapp_number", "business_id"]
            }
        },
        "server": {"url": f"{backend_url}/book-appointment"}
    }

def _collect_patient_details_function() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "collect_patient_details",
            "description": "Call this to open a screen form for the patient's name and phone number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                    "reason": {"type": "string"}
                },
                "required": ["date", "time", "reason"]
            }
        }
    }

def _escalate_to_human_tool(backend_url: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Call this when the rag_query confidence is low or patient asks for a human.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caller_context": {"type": "string"},
                    "question": {"type": "string"},
                    "business_id": {"type": "string"}
                },
                "required": ["caller_context", "question", "business_id"]
            }
        },
        "server": {"url": f"{backend_url}/escalate"}
    }

def _lookup_patient_tool(backend_url: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "lookup_patient",
            "description": "Call this to look up a returning patient's details by their phone number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string", "description": "Patient's phone number e.g. +15551234567"},
                    "business_id": {"type": "string"}
                },
                "required": ["phone_number", "business_id"]
            }
        },
        "server": {"url": f"{backend_url}/lookup-patient"}
    }

def _build_assistant_payload(
    business_name: str,
    category: str,
    backend_url: str,
    elevenlabs_voice_id: str | None = None,
) -> dict:
    voice_id = elevenlabs_voice_id or settings.ELEVENLABS_VOICE_ID

    return {
        "name": f"{business_name} AI Receptionist",
        "model": {
            "provider": "groq",
            "model": settings.GROQ_MODEL,
            "systemPrompt": _build_system_prompt(),
            "temperature": 0.3,
            "tools": [
                _rag_query_tool(backend_url),
                _lookup_patient_tool(backend_url),
                _collect_patient_details_function(),
                _book_appointment_tool(backend_url),
                _escalate_to_human_tool(backend_url),
            ],
        },
        "voice": {
            "provider": "11labs",
            "voiceId": voice_id,
            "stability": 0.5,
            "similarityBoost": 0.75,
        },
        "firstMessage": "Hello! You've reached Fit Smile Dental Clinic. I'm Aria, your AI receptionist. How can I help you today?",
        # End-of-call farewell — Vapi speaks this when the call concludes
        "endCallMessage": "Thank you for calling Fit Smile Dental Clinic. We look forward to seeing you. Have a wonderful day, goodbye!",
        # Phrases that trigger Vapi to end the call gracefully
        "endCallPhrases": ["goodbye", "bye bye", "have a great day", "see you soon", "thank you goodbye"],
        # Give patient time to finish speaking before agent responds
        "silenceTimeoutSeconds": 30,
        "responseDelaySeconds": 1.5,
        "clientMessages": ["function-call", "tool-calls"],
        "serverMessages": ["tool-calls", "end-of-call-report", "status-update"],
    }


# ── Public API ─────────────────────────────────────────────────────────────

async def create_assistant(
    business_name: str = "Demo Business",
    category: str = "clinic",
    backend_url: str | None = None,
    elevenlabs_voice_id: str | None = None,
) -> dict:
    """
    Create a new Vapi assistant and return the full response dict.
    Store the returned `id` as VAPI_ASSISTANT_ID in .env.
    """
    url = settings.BACKEND_URL if backend_url is None else backend_url
    payload = _build_assistant_payload(business_name, category, url, elevenlabs_voice_id)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{VAPI_BASE}/assistant",
            headers=HEADERS,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


async def update_assistant(
    assistant_id: str,
    business_name: str,
    category: str,
    backend_url: str | None = None,
    elevenlabs_voice_id: str | None = None,
) -> dict:
    """
    Update an existing Vapi assistant (e.g. after a business edits their config).
    Uses PATCH so only the provided fields are changed.
    """
    url = settings.BACKEND_URL if backend_url is None else backend_url
    payload = _build_assistant_payload(business_name, category, url, elevenlabs_voice_id)

    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{VAPI_BASE}/assistant/{assistant_id}",
            headers=HEADERS,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


async def get_assistant(assistant_id: str) -> dict:
    """Fetch current assistant config from Vapi."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{VAPI_BASE}/assistant/{assistant_id}",
            headers=HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
