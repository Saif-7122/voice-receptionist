import asyncio, os, json
from dotenv import load_dotenv
load_dotenv()
from vapi_client import get_assistant

async def main():
    conf = await get_assistant(os.getenv("VAPI_ASSISTANT_ID"))
    print("=== ASSISTANT VERIFICATION ===")
    print("Name:", conf.get("name"))
    print("First message:", conf.get("firstMessage"))
    print("Silence timeout:", conf.get("silenceTimeoutSeconds"))
    print("Response delay:", conf.get("responseDelaySeconds"))
    print("Client messages:", conf.get("clientMessages"))
    model = conf.get("model", {})
    prompt = model.get("systemPrompt", "")
    print("System prompt (first 300 chars):", prompt[:300])
    print()
    for tool in model.get("tools", []):
        fn = tool.get("function", {})
        has_server = "server" in tool
        required = fn.get("parameters", {}).get("required", [])
        print(f"  Tool: {fn['name']} | server_tool={has_server} | required={required}")

asyncio.run(main())
