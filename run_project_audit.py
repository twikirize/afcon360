import asyncio
import os
from google.antigravity import Agent, LocalAgentConfig


# Helper to read your .env.local file manually if needed
def load_env_local():
    """Manually parse .env.local to load the GEMINI_API_KEY into environment variables."""
    env_path = os.path.join(os.path.dirname(__file__), '.env.local')
    if os.path.exists(env_path):
        print("txt Found .env.local file. Loading keys...")
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines, comments, or lines without an equals sign
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    # Remove accidental spaces or surrounding quotes
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")

async def main():
    # 1. Load the keys into the system environment
    load_env_local()

    # 2. Grab the key (or paste your 'AIzaSy...' key directly into the quotes below)
    gemini_key = os.getenv("GEMINI_API_KEY") or "YOUR_PASTED_API_KEY_HERE"

    # 3. Pass the key explicitly into the Antigravity config
    config = LocalAgentConfig(
        api_key=gemini_key,
        system_instructions=(
            "You are a master backend systems engineer. Your job is to analyze the "
            "entire local directory layout for afcon360_app. Scan all python blueprints, "
            "routes.py files, database models, and HTML templates."
        )
    )

    # 4. Boot up the agent harness locally
    async with Agent(config) as agent:
        print("🚀 Local Antigravity Engine started inside PyCharm...")

        prompt = (
            "Scan the templates and routes. Look for any variable naming mismatches "
            "(like 'identifier' vs 'event_slug') across different application blueprints. "
            "Point out which files have conflicts and provide drops-in-place fixes."
        )

        print("🧠 Auditing codebase structure (reading local files)...")
        response = await agent.chat(prompt)

        print("\n=== SYSTEM ARCHITECTURE REPORT ===\n")
        print(await response.text())


if __name__ == "__main__":
    asyncio.run(main())