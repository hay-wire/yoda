"""Phase 4 privacy option: swap Claude for a fully local model for
classification of raw content, so nothing leaves the machine. Enable with
PRIVACY_MODE=local in .env.

Requires Ollama running locally (https://ollama.com) with a model already
pulled, e.g. `ollama pull llama3.1`. This is the one piece of Phase 4 that
runs entirely offline - it trades classification quality for not sending
raw email/WhatsApp content to any external API at all, Claude included.
"""

import json
import os

import requests

from brain.claude_agent import PROMPT_TEMPLATE, _extract_json_array, _format_messages

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")


def classify_messages(company, channel, messages, timeout=120):
    if not messages:
        return []

    prompt = PROMPT_TEMPLATE.format(company=company, channel=channel, messages=_format_messages(messages))
    response = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    response.raise_for_status()
    return json.loads(_extract_json_array(response.json()["response"]))
