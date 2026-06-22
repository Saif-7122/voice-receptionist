import asyncio
import os
from vapi_client import create_assistant

async def main():
    print("Creating new Vapi assistant...")
    try:
        res = await create_assistant(
            business_name="Fit Smile Dental",
            category="clinic",
            backend_url="https://licorice-agonize-spill.ngrok-free.dev",
            elevenlabs_voice_id="21m00Tcm4TlvDq8ikWAM"
        )
        print("Create successful!")
        print(f"NEW_ASSISTANT_ID={res['id']}")
    except Exception as e:
        import httpx
        if isinstance(e, httpx.HTTPStatusError):
            print("HTTP Error:", e.response.text)
        raise

if __name__ == "__main__":
    asyncio.run(main())
