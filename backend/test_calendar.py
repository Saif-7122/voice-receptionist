import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from calendar_client import create_event

async def main():
    try:
        res = await create_event(
            patient_name="Test Patient",
            age="30",
            reason="Checkup",
            date="2026-06-25",
            time="14:00",
            doctor_name="Dr. Smith"
        )
        print("Success:", res)
    except Exception as e:
        print("Error:", repr(e))

if __name__ == "__main__":
    asyncio.run(main())
