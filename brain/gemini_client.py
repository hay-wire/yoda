import os

from google import genai

_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def generate(prompt):
    """Only ever called with already-structured/aggregate data by the
    router - never raw email/WhatsApp content."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(model=_MODEL, contents=prompt)
    return response.text.strip()
