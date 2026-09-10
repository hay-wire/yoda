import json
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent / "whatsapp_baileys.js"


def fetch_new_messages(since_timestamp_ms=0, timeout=60):
    """Shells out to the Baileys sidecar: reconnect -> fetch -> disconnect,
    once per wake cycle. Never sends anything."""
    result = subprocess.run(
        ["node", str(SCRIPT_PATH), str(since_timestamp_ms)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"whatsapp_baileys.js failed: {result.stderr.strip()}")
    return json.loads(result.stdout.strip() or "[]")
