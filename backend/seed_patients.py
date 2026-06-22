import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client, Client
from config import settings

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

async def seed_data():
    business_id = "12345" # Using the test business_id defined in the prompt config

    print("Seeding patients...")
    # Patient 1: Active membership
    p1 = supabase.table("patients").insert({
        "business_id": business_id,
        "name": "Alice Smith",
        "phone_number": "+15551112222",
        "age": 34,
        "membership_status": "active",
        "membership_expiry": "2027-12-31"
    }).execute()
    p1_id = p1.data[0]["id"]

    # Patient 2: Expired membership
    p2 = supabase.table("patients").insert({
        "business_id": business_id,
        "name": "Bob Jones",
        "phone_number": "+15553334444",
        "age": 45,
        "membership_status": "expired",
        "membership_expiry": "2025-01-01"
    }).execute()
    p2_id = p2.data[0]["id"]

    print("Seeding treatment history...")
    # Alice's treatments
    supabase.table("treatment_history").insert([
        {
            "patient_id": p1_id,
            "visit_date": "2026-05-15",
            "treatment": "Routine Cleaning",
            "doctor_name": "Dr. Smith",
            "notes": "No cavities. Gums look healthy."
        },
        {
            "patient_id": p1_id,
            "visit_date": "2025-11-10",
            "treatment": "X-Ray and Exam",
            "doctor_name": "Dr. Smith",
            "notes": "Wisdom teeth stable."
        }
    ]).execute()

    # Bob's treatments
    supabase.table("treatment_history").insert([
        {
            "patient_id": p2_id,
            "visit_date": "2025-08-20",
            "treatment": "Root Canal",
            "doctor_name": "Dr. Adams",
            "notes": "Tooth 14 treated. Temporary crown placed."
        }
    ]).execute()

    # Add an upcoming appointment for Alice
    supabase.table("appointments").insert({
        "business_id": business_id,
        "patient_id": p1_id,
        "patient_name": "Alice Smith",
        "patient_whatsapp": "+15551112222",
        "confirmed_date": "Today",
        "confirmed_time": "2:00 PM",
        "confirmed_reason": "Follow-up",
        "status": "booked"
    }).execute()

    print("Seed complete! Test numbers:")
    print("  Active: +15551112222 (Alice Smith)")
    print("  Expired: +15553334444 (Bob Jones)")

if __name__ == "__main__":
    asyncio.run(seed_data())
