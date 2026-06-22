"""
models.py — Pydantic request/response models and Supabase table schema references.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Business ──────────────────────────────────────────────────────────────────

class BusinessCreate(BaseModel):
    name: str
    category: Optional[str] = None          # gym | cafe | clinic | restaurant
    description: Optional[str] = None
    hours: Optional[dict[str, str]] = None  # { "mon": "9am-9pm", ... }
    location: Optional[str] = None
    phone: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None


class BusinessResponse(BusinessCreate):
    id: str
    owner_id: str
    vapi_assistant_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── FAQ / Knowledge ───────────────────────────────────────────────────────────

class FAQCreate(BaseModel):
    question: str
    answer: str


class FAQResponse(FAQCreate):
    id: str
    business_id: str
    created_at: Optional[datetime] = None


# ── RAG Query ─────────────────────────────────────────────────────────────────

class RAGQueryRequest(BaseModel):
    """Received from Vapi when the LLM calls the rag_query server tool."""
    query: str
    business_id: str
    call_id: Optional[str] = None


class RAGQueryResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)


# ── Appointment Booking ───────────────────────────────────────────────────────

class BookAppointmentRequest(BaseModel):
    """Received from Vapi after collect_patient_details resolves on the frontend."""
    confirmed_date: str
    confirmed_time: str
    confirmed_reason: Optional[str] = None
    patient_name: str
    patient_whatsapp_number: str
    business_id: str
    call_id: Optional[str] = None


class BookAppointmentResponse(BaseModel):
    success: bool
    confirmation_code: str
    message: str


# ── Call Log ──────────────────────────────────────────────────────────────────

class CallLogCreate(BaseModel):
    business_id: str
    vapi_call_id: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    escalated: bool = False
    duration_sec: Optional[int] = None
    caller_info: Optional[dict[str, Any]] = None


# ── Vapi Webhook ──────────────────────────────────────────────────────────────

class VapiWebhookPayload(BaseModel):
    """Generic Vapi webhook envelope — actual shape varies by event type."""
    type: Optional[str] = None
    call: Optional[dict[str, Any]] = None
    message: Optional[dict[str, Any]] = None
    tool_call: Optional[dict[str, Any]] = None

    class Config:
        extra = "allow"   # Vapi may send extra fields depending on event
