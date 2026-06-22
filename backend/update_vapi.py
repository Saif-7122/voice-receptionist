import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from vapi_client import update_assistant, get_assistant

async def main():
    print("Updating assistant...")
    try:
        res = await update_assistant(
            assistant_id=os.getenv("VAPI_ASSISTANT_ID"),
            business_name="Fit Smile Dental",
            category="clinic",
            backend_url="https://licorice-agonize-spill.ngrok-free.dev",
            elevenlabs_voice_id="21m00Tcm4TlvDq8ikWAM"
        )
        print("Update successful!")
    except Exception as e:
        import httpx
        if isinstance(e, httpx.HTTPStatusError):
            print("HTTP Error:", e.response.text)
        raise
    
    print("\nFetching back config to verify...")
    conf = await get_assistant(os.getenv("VAPI_ASSISTANT_ID"))

    for tool in conf.get("tools", []):
        if "server" in tool:
            print(f"Tool {tool['function']['name']} URL: {tool['server']['url']}")
        else:
            print(f"Tool {tool['function']['name']} (Client side)")

if __name__ == "__main__":
    asyncio.run(main())
