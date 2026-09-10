import json
import subprocess

CLASSIFY_PROMPT_TEMPLATE = """You are extracting work items from raw messages for a personal work-tracking system.

Company for this batch: {company}
Channel: {channel}

Raw messages:
{messages}

For each message that represents an actionable work item (a task, request, question needing \
a reply, or commitment), output one object with exactly these fields:
- item: short description (string)
- company: "{company}"
- channel: "{channel}"
- stage: one of "new", "in progress", "waiting on them", "stalled"
- next_action: what needs to happen next (string, or null)
- due_date: ISO date "YYYY-MM-DD" if a deadline is mentioned, else null
- urgency: one of "low", "medium", "high"
- source_ref: the message id given in "[id=...]" for that message

Skip messages that are pure noise (newsletters, notifications, no action needed).

Respond with ONLY a JSON array of these objects (an empty array if nothing is actionable) \
and no other text.
"""

# Kept as a separate constant (not folded into CLASSIFY_PROMPT_TEMPLATE) so
# brain/local_client.py can reuse the exact same classification prompt.
PROMPT_TEMPLATE = CLASSIFY_PROMPT_TEMPLATE

DRAFT_PROMPT_TEMPLATE = """Draft a short, professional reply for this work item. \
This is a draft only, for the user to review and send manually - do not imply it has been sent.

Company: {company}
Channel: {channel}
Item: {item}
Next action: {next_action}

Write only the draft reply text, 3-6 sentences, no subject line, no preamble.
"""


def classify_messages(company, channel, messages, timeout=120):
    """Raw content in -> Claude. Runs via `claude -p` so calls draw on the
    logged-in Pro/Max subscription rather than paid API billing."""
    if not messages:
        return []

    formatted = _format_messages(messages)
    prompt = CLASSIFY_PROMPT_TEMPLATE.format(company=company, channel=channel, messages=formatted)
    output = _run_claude(prompt, timeout)
    return json.loads(_extract_json_array(output))


def draft_reply(item, timeout=60):
    """Phase 4: suggest a reply. Never sends anything - the caller (the
    Telegram /draft command) only ever returns this text for the user to
    copy and send themselves."""
    prompt = DRAFT_PROMPT_TEMPLATE.format(
        company=item.get("company", ""),
        channel=item.get("channel", ""),
        item=item.get("item", ""),
        next_action=item.get("next_action") or "not specified",
    )
    return _run_claude(prompt, timeout)


def compose(prompt, timeout=60):
    """Generic plain-text completion - the fallback brain for wording tasks
    when the Gemini router path isn't used or fails."""
    return _run_claude(prompt, timeout)


def _run_claude(prompt, timeout):
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _format_messages(messages):
    return "\n\n".join(
        f"[id={m['id']}] From: {m['from']} | Date: {m['date']} | Subject: {m.get('subject', '')}\n{m['body']}"
        for m in messages
    )


def _extract_json_array(text):
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON array found in Claude output: {text[:200]!r}")
    return text[start : end + 1]
