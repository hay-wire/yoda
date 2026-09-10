"""Decides Claude vs Gemini (vs a local model) per call.

Split is by data sensitivity, not task type: raw content always goes to
`classify`, which never touches Gemini. Gemini is only reachable through
`compose` and only when the caller explicitly passes structured_only=True -
the router never infers that a prompt is "safe" from its content, per the
mitigation for "router misclassifies something sensitive as safe": default
to Claude when in doubt.
"""

from brain import claude_agent, gemini_client, local_client
from config import PRIVACY_MODE


def classify(company, channel, messages, persona=""):
    if PRIVACY_MODE == "local":
        return local_client.classify_messages(company, channel, messages, persona=persona)
    return claude_agent.classify_messages(company, channel, messages, persona=persona)


def compose(prompt, structured_only=False):
    if structured_only:
        try:
            return gemini_client.generate(prompt)
        except Exception:
            pass  # Gemini unavailable/rate-limited - fall through to Claude
    return claude_agent.compose(prompt)
