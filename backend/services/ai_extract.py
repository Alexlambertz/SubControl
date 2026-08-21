"""
One-shot (non-streaming) structured-extraction helpers for AI-assisted
insurance discovery and document import.

Unlike ``ai_chat.py`` (which streams a conversational reply and dispatches
OpenAI-style tool calls), the functions here make a single non-streaming
call and ask the model to return a JSON object directly. They never touch
the database — callers are responsible for validating and persisting
anything the AI suggests, and only after the user has explicitly confirmed
it (nothing here writes data).

AI output is never trusted blindly: both functions defensively parse the
response and silently drop malformed entries (bad JSON, wrong types,
references to IDs that don't exist) rather than raising or persisting
hallucinated data.
"""

from __future__ import annotations

import json
import logging
from typing import Any, NamedTuple

import aiosqlite

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment,misc]

from backend.services.ai_chat import _get_settings
from backend.services.attachments import attachments_dir
from backend.services.document_content import prepare_document_content

logger = logging.getLogger(__name__)

VALID_INTERVALS = {"daily", "weekly", "monthly", "quarterly", "half-year", "yearly"}

_SUBSCRIPTION_FIELDS = (
    "name, provider_name, recurring_interval "
    "(one of daily/weekly/monthly/quarterly/half-year/yearly), recurring_date "
    "(YYYY-MM-DD, last payment date), end_date (YYYY-MM-DD, optional), amount "
    "(number), currency (ISO 4217 code, default EUR), category_name (optional)"
)

_INSURANCE_FIELDS = (
    "name, insurer, policy_number (optional), recurring_interval "
    "(one of daily/weekly/monthly/quarterly/half-year/yearly), recurring_date "
    "(YYYY-MM-DD, last/next premium payment date), end_date (YYYY-MM-DD, optional), "
    "amount (number, premium per interval), currency (ISO 4217 code, default EUR), "
    "category_name (optional), notes (optional)"
)


class AiConfig(NamedTuple):
    api_url: str
    api_key: str
    model: str


async def resolve_ai_config(db: aiosqlite.Connection) -> AiConfig | None:
    """
    Resolve AI connection settings using the same DB-overrides-env precedence
    as ``ai_chat.py``. Returns ``None`` when no API URL is configured at all.
    """
    from backend.config import settings as env_cfg

    db_settings = await _get_settings(db)
    api_url = db_settings.get("ai_api_url", "") or env_cfg.ai_api_url
    api_key = db_settings.get("ai_api_key", "") or env_cfg.ai_api_key or "none"
    model = db_settings.get("ai_model", "") or env_cfg.ai_model or "gpt-4o-mini"

    if not api_url:
        return None
    return AiConfig(api_url=api_url, api_key=api_key, model=model)


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("AI response was not valid JSON")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _content_to_message(content: dict[str, Any], instruction: str) -> Any:
    """
    Build a chat message ``content`` value (plain string or vision parts
    list) from an ``ai_extract`` content dict — shared by every function
    here that takes document text/images as input.
    """
    if content["kind"] == "text":
        return f"{instruction}\n\nDocument text:\n{content['text']}"

    data_urls = content["data_urls"]
    page_note = f" ({len(data_urls)} pages)" if len(data_urls) > 1 else ""
    return [
        {"type": "text", "text": f"{instruction}{page_note}."},
        *({"type": "image_url", "image_url": {"url": url}} for url in data_urls),
    ]


# ---------------------------------------------------------------------------
# Find Insurances — classify existing subscriptions
# ---------------------------------------------------------------------------


async def detect_insurance_candidates(
    subscriptions: list[dict[str, Any]], config: AiConfig
) -> list[dict[str, Any]]:
    """
    Ask the AI which of *subscriptions* look like insurance policies.

    Each item in *subscriptions* must have: id, name, provider_name, amount,
    currency, recurring_interval, category_name.

    Returns a list of candidate dicts (subset of the input, augmented with
    ``suggested_insurer``, ``suggested_category``, ``confidence``, ``reason``)
    — entries referencing an unknown subscription id are dropped.
    """
    if AsyncOpenAI is None or not subscriptions:
        return []

    by_id = {s["id"]: s for s in subscriptions}
    sub_lines = "\n".join(
        f"- id: {s['id']} | {s['name']} | {s['provider_name'] or 'no provider'}"
        f" | {s['amount']} {s['currency']}/{s['recurring_interval']}"
        + (f" | category: {s['category_name']}" if s.get("category_name") else "")
        for s in subscriptions
    )

    system_prompt = (
        "You identify which recurring subscriptions in a personal finance app "
        "are actually insurance policies (health, car, home, liability, legal, "
        "travel, life, pet insurance, etc.) rather than genuine subscriptions "
        "(streaming, software, memberships). Judge by name and provider — "
        "well-known insurers and words like 'Versicherung', 'insurance', "
        "'assurance', 'HUK', 'ARAG', 'ADAC', 'Allianz' are strong signals.\n\n"
        "Respond with ONLY a JSON object of this exact shape, no prose:\n"
        '{"candidates": [{"subscription_id": "<id from the list>", '
        '"insurer": "<best-guess insurer/company name>", '
        '"category_name": "<suggested category, e.g. Insurance>", '
        '"confidence": "high|medium|low", '
        '"reason": "<one short sentence>"}]}\n'
        "Only include subscriptions you believe are insurance policies. "
        "Use the exact subscription_id values given — never invent one. "
        "If none look like insurance, return an empty candidates array."
    )

    client = AsyncOpenAI(base_url=config.api_url, api_key=config.api_key)
    try:
        response = await client.chat.completions.create(
            model=config.model,
            stream=False,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Subscriptions:\n{sub_lines}"},
            ],
        )
    except Exception:
        logger.exception("AI candidate-detection call failed")
        return []

    content = response.choices[0].message.content if response.choices else None
    parsed = _parse_json_object(content)
    raw_candidates = parsed.get("candidates")
    if not isinstance(raw_candidates, list):
        return []

    results: list[dict[str, Any]] = []
    for c in raw_candidates:
        if not isinstance(c, dict):
            continue
        sub = by_id.get(c.get("subscription_id"))
        if sub is None:
            continue
        confidence = c.get("confidence") if c.get("confidence") in ("high", "medium", "low") else "low"
        results.append(
            {
                "subscription_id": sub["id"],
                "name": sub["name"],
                "provider_name": sub.get("provider_name"),
                "amount": sub["amount"],
                "currency": sub["currency"],
                "recurring_interval": sub["recurring_interval"],
                "suggested_insurer": str(c.get("insurer") or sub.get("provider_name") or sub["name"]),
                "suggested_category": str(c.get("category_name") or sub.get("category_name") or "Insurance"),
                "confidence": confidence,
                "reason": str(c.get("reason") or ""),
            }
        )
    return results


# ---------------------------------------------------------------------------
# AI Document Import — extract records from an uploaded document
# ---------------------------------------------------------------------------


async def extract_records_from_document(
    content: dict[str, Any], config: AiConfig
) -> list[dict[str, Any]]:
    """
    Ask the AI to extract subscription/insurance records from a document.

    *content* is either ``{"kind": "text", "text": "..."}`` (extracted PDF
    text) or ``{"kind": "image", "data_urls": ["data:image/...;base64,...", ...]}``
    (one or more page images — e.g. a photo/screenshot, or pages rendered
    from a scanned/image-only PDF — sent as vision message parts).

    Returns a list of ``{"type": "subscription"|"insurance", "confidence": ...,
    "fields": {...}}`` dicts. Entries with an unrecognised type or missing
    required fields are dropped.
    """
    if AsyncOpenAI is None:
        return []

    system_prompt = (
        "You extract billing information from documents (insurance policies, "
        "subscription invoices, order confirmations) for a personal finance app. "
        "Decide whether the document describes an INSURANCE policy or a regular "
        "SUBSCRIPTION, then extract its fields.\n\n"
        f"Subscription fields: {_SUBSCRIPTION_FIELDS}\n"
        f"Insurance fields: {_INSURANCE_FIELDS}\n\n"
        "Respond with ONLY a JSON object of this exact shape, no prose:\n"
        '{"records": [{"type": "subscription|insurance", '
        '"confidence": "high|medium|low", "fields": { ... }}]}\n'
        "A single document usually yields exactly one record, but include more "
        "if the document genuinely lists several distinct policies/subscriptions. "
        "Omit fields you cannot determine rather than guessing wildly. "
        "If the document doesn't look like either, return an empty records array."
    )

    user_content = _content_to_message(content, "Extract billing information from this document")

    client = AsyncOpenAI(base_url=config.api_url, api_key=config.api_key)
    try:
        response = await client.chat.completions.create(
            model=config.model,
            stream=False,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
    except Exception:
        logger.exception("AI document-extraction call failed")
        return []

    content_str = response.choices[0].message.content if response.choices else None
    parsed = _parse_json_object(content_str)
    raw_records = parsed.get("records")
    if not isinstance(raw_records, list):
        return []

    results: list[dict[str, Any]] = []
    for r in raw_records:
        if not isinstance(r, dict):
            continue
        record_type = r.get("type")
        if record_type not in ("subscription", "insurance"):
            continue
        fields = r.get("fields")
        if not isinstance(fields, dict) or not fields.get("name") or not fields.get("amount"):
            continue
        interval = fields.get("recurring_interval")
        if interval not in VALID_INTERVALS:
            fields["recurring_interval"] = "monthly"
        confidence = r.get("confidence") if r.get("confidence") in ("high", "medium", "low") else "low"
        results.append({"type": record_type, "confidence": confidence, "fields": fields})
    return results


# ---------------------------------------------------------------------------
# Attachment analysis — compare a document against an existing record
# ---------------------------------------------------------------------------

_SUBSCRIPTION_UPDATE_FIELDS = {
    "name", "provider_name", "recurring_interval", "recurring_date",
    "end_date", "amount", "currency", "category_name",
}
_INSURANCE_UPDATE_FIELDS = {
    "name", "insurer", "policy_number", "recurring_interval", "recurring_date",
    "end_date", "amount", "currency", "category_name", "notes",
}


async def extract_field_updates(
    existing_fields: dict[str, Any],
    kind: str,
    content: dict[str, Any],
    config: AiConfig,
) -> dict[str, Any]:
    """
    Compare a newly uploaded document against *existing_fields* (the current
    stored values for a subscription or insurance) and return only the
    fields whose document-derived value actually differs.

    *kind* is ``"subscription"`` or ``"insurance"`` — selects which field
    set/description is used. *content* is the same shape
    :func:`extract_records_from_document` takes (text or one or more
    page images).

    The response is never trusted blindly: any key outside the known field
    set for *kind*, any value that already matches ``existing_fields``, and
    any invalid ``recurring_interval`` are dropped server-side — regardless
    of whether the model followed the "omit unchanged fields" instruction.
    """
    if AsyncOpenAI is None:
        return {}

    if kind == "insurance":
        field_descr, allowed_fields = _INSURANCE_FIELDS, _INSURANCE_UPDATE_FIELDS
    else:
        field_descr, allowed_fields = _SUBSCRIPTION_FIELDS, _SUBSCRIPTION_UPDATE_FIELDS

    system_prompt = (
        f"You review a newly uploaded document against the CURRENT stored data for a "
        f"{kind} in a personal finance app, and identify which fields should be UPDATED "
        "based on what the document says.\n\n"
        f"Fields: {field_descr}\n\n"
        f"Current data: {json.dumps(existing_fields)}\n\n"
        "Respond with ONLY a JSON object of this exact shape, no prose:\n"
        '{"updates": {"<field>": <new value>, ...}}\n'
        "Include a field ONLY if the document clearly states a value that is DIFFERENT "
        "from the current data shown above. Omit any field that matches the current "
        "value, that the document doesn't mention, or that you're not confident about. "
        "If nothing should change, return an empty updates object."
    )

    user_content = _content_to_message(
        content, "Compare this document against the current data and identify any changed fields"
    )

    client = AsyncOpenAI(base_url=config.api_url, api_key=config.api_key)
    try:
        response = await client.chat.completions.create(
            model=config.model,
            stream=False,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
    except Exception:
        logger.exception("AI field-update comparison call failed")
        return {}

    content_str = response.choices[0].message.content if response.choices else None
    parsed = _parse_json_object(content_str)
    raw_updates = parsed.get("updates")
    if not isinstance(raw_updates, dict):
        return {}

    results: dict[str, Any] = {}
    for field, value in raw_updates.items():
        if field not in allowed_fields:
            continue
        if field == "recurring_interval" and value not in VALID_INTERVALS:
            continue
        if value == existing_fields.get(field):
            continue
        results[field] = value
    return results


async def analyze_attachment_for_updates(
    db: aiosqlite.Connection,
    *,
    storage_path: str,
    filename: str,
    content_type: str,
    existing_fields: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    """
    Best-effort wrapper around :func:`extract_field_updates` for a just-saved
    attachment: resolves AI config, reads the file back from disk (the
    caller's ``UploadFile`` stream is already consumed by ``save_attachment``),
    and prepares it for analysis. Used by both the subscription and insurance
    attachment-upload routes.

    Never raises and never blocks the upload it's called from — any failure
    (AI not configured, unsupported file type, AI call error) simply yields
    an empty dict, so attachment storage keeps working regardless of AI setup.
    """
    config = await resolve_ai_config(db)
    if config is None:
        return {}
    try:
        data = (attachments_dir() / storage_path).read_bytes()
        content = await prepare_document_content(filename, content_type, data)
        if content is None:
            return {}
        return await extract_field_updates(existing_fields, kind, content, config)
    except Exception:
        logger.exception("Attachment analysis failed for %s", storage_path)
        return {}
