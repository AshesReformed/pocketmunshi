"""
PocketMunshi extraction: turn a free-form Urdu/English code-switched
transcript into structured transaction data via a Groq-hosted LLM.

STACK CONSTRAINT: LLM extraction only (Groq-hosted), NOT regex/keyword
matching -- free-form code-switched speech isn't reliably parseable that way.

MODEL NOTE: originally speced as "llama-3.1-8b-instant", but that model is
now gated behind a paid Groq tier and returns a 404 on free-tier keys
("model_not_found" -- checked live against console.groq.com/docs/models on
2026-09-12). Switched to "openai/gpt-oss-20b", which is available on the
free tier and handles structured JSON output well. If your account's
available models differ, run:
    python -c "from groq import Groq; [print(m.id) for m in Groq(api_key='YOUR_KEY').models.list().data]"
and swap MODEL below to whatever general-purpose chat model that lists.

Design principle: under-extracting is fine (a human confirms before saving);
a confident wrong guess is worse than an honest null. The prompt below is
kept short and few-shot rather than verbose, to hold down per-call token
cost on a hackathon/demo budget.
"""

import json

from groq import Groq

MODEL = "openai/gpt-oss-20b"

_VALID_TYPES = {"credit_given", "payment_received", "sale", "unknown"}

_NULL_RESULT = {"customer_name": None, "amount": None, "type": "unknown"}

_SYSTEM_PROMPT = """You extract structured data from ONE spoken shopkeeper transaction (Urdu/English code-switched, e.g. Roman Urdu). Reply with ONLY minified JSON, no prose:
{"customer_name": string|null, "amount": number|null, "type": "credit_given"|"payment_received"|"sale"|"unknown"}

type meanings:
- credit_given: shop gave goods/money to customer ON CREDIT (customer now owes more) -- e.g. "udhaar liya/diya", "udhaar par"
- payment_received: customer PAID BACK some/all of what they owed -- e.g. "paise wapis kiye", "udhaar utar diya", "paid back"
- sale: a plain cash sale, no credit involved
- unknown: transaction type can't be determined

Rules:
- If ANY field is not clearly stated, output null for it (or "unknown" for type) instead of guessing. A confident wrong guess is worse than null.
- amount must be a plain number (no currency symbols/words).
- customer_name is the person's name only, not a title or pronoun.

Examples:
"Ali ne paanch sau rupay udhaar liya" -> {"customer_name":"Ali","amount":500,"type":"credit_given"}
"Fatima paid back 300 rupees" -> {"customer_name":"Fatima","amount":300,"type":"payment_received"}
"maine do sau rupay ka saman becha cash pe" -> {"customer_name":null,"amount":200,"type":"sale"}
"kuch samajh nahi aaya" -> {"customer_name":null,"amount":null,"type":"unknown"}
"""


def _coerce(raw: dict) -> dict:
    """Validate/clean a parsed dict against the schema, defaulting anything malformed."""
    customer_name = raw.get("customer_name")
    if not isinstance(customer_name, str) or not customer_name.strip():
        customer_name = None
    else:
        customer_name = customer_name.strip()

    amount = raw.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        amount = None
    else:
        amount = float(amount)

    txn_type = raw.get("type")
    if txn_type not in _VALID_TYPES:
        txn_type = "unknown"

    return {"customer_name": customer_name, "amount": amount, "type": txn_type}


def extract_transaction(transcript: str, api_key: str) -> dict:
    """
    Send transcript to a Groq LLM and return
    {"customer_name": str|None, "amount": float|None,
     "type": "credit_given"|"payment_received"|"sale"|"unknown"}.

    Never raises on a malformed/unparseable model response -- falls back to
    the all-null/"unknown" shape instead, since a human always confirms the
    result before it's saved. Network/auth failures from the Groq client
    DO propagate, so the caller can tell "model was unsure" apart from
    "the API call failed."
    """
    if not transcript or not transcript.strip():
        return dict(_NULL_RESULT)

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": transcript.strip()},
        ],
    )

    content = response.choices[0].message.content

    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return dict(_NULL_RESULT)
        return _coerce(parsed)
    except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return dict(_NULL_RESULT)
