"""
Insurances router — CRUD for insurance policies within a bucket, plus
attachment upload/download/delete for policy documents (e.g. conditions PDF).

Routes
------
GET    /api/buckets/{bucket_id}/insurances                                    List insurances
POST   /api/buckets/{bucket_id}/insurances                                    Create insurance
GET    /api/buckets/{bucket_id}/insurances/{insurance_id}                     Get single insurance
PUT    /api/buckets/{bucket_id}/insurances/{insurance_id}                     Update insurance
DELETE /api/buckets/{bucket_id}/insurances/{insurance_id}                     Delete insurance
POST   /api/buckets/{bucket_id}/insurances/{insurance_id}/attachments         Upload attachment
GET    /api/buckets/{bucket_id}/insurances/{insurance_id}/attachments/{id}    Download attachment
DELETE /api/buckets/{bucket_id}/insurances/{insurance_id}/attachments/{id}    Delete attachment
GET    /api/buckets/{bucket_id}/insurances/export                             Export as CSV

Category records are created on-the-fly when a new name is supplied, reusing
the same helper as the subscriptions router so insurances and subscriptions
share one category list.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, field_validator

from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user
from backend.routers.subscriptions import (
    VALID_INTERVALS,
    _check_bucket_access,
    _get_bucket_or_404,
    _get_or_create_category,
    _get_or_create_owner,
)
from backend.services.ai_extract import (
    analyze_attachment_for_updates,
    detect_insurance_candidates,
    resolve_ai_config,
)
from backend.services.attachments import (
    attachments_dir,
    delete_attachment_file,
    save_attachment,
)
from backend.services.history import (
    INSURANCE_HISTORY_FIELDS,
    HistoryEntryResponse,
    get_history,
    record_changes,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["insurances"])

# Columns written to the exported CSV
_EXPORT_COLUMNS = [
    "name", "insurer", "policy_number", "recurring_interval", "recurring_date",
    "end_date", "amount", "currency", "category", "notes",
]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InsuranceCreate(BaseModel):
    name: str
    insurer: str
    policy_number: Optional[str] = None
    recurring_interval: str
    recurring_date: Optional[str] = None
    end_date: Optional[str] = None
    amount: float = 0.0
    currency: str = "EUR"
    category_name: Optional[str] = None
    owner_name: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("name", "insurer")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("recurring_interval")
    @classmethod
    def valid_interval(cls, v: str) -> str:
        if v not in VALID_INTERVALS:
            raise ValueError(
                f"recurring_interval must be one of {sorted(VALID_INTERVALS)}"
            )
        return v


class InsuranceUpdate(BaseModel):
    name: Optional[str] = None
    insurer: Optional[str] = None
    policy_number: Optional[str] = None
    recurring_interval: Optional[str] = None
    recurring_date: Optional[str] = None
    end_date: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    category_name: Optional[str] = None
    owner_name: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("recurring_interval")
    @classmethod
    def valid_interval(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_INTERVALS:
            raise ValueError(
                f"recurring_interval must be one of {sorted(VALID_INTERVALS)}"
            )
        return v


class AttachmentResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: str


class AttachmentUploadResult(BaseModel):
    attachment: AttachmentResponse
    suggested_updates: dict[str, Any] = {}


class InsuranceResponse(BaseModel):
    id: str
    bucket_id: str
    name: str
    insurer: str
    policy_number: Optional[str] = None
    recurring_interval: str
    recurring_date: Optional[str] = None
    end_date: Optional[str] = None
    amount: float
    currency: str
    category_name: Optional[str] = None
    owner_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    updated_at: str
    attachments: list[AttachmentResponse] = []


class DetectCandidate(BaseModel):
    subscription_id: str
    name: str
    provider_name: Optional[str] = None
    amount: float
    currency: str
    recurring_interval: str
    suggested_insurer: str
    suggested_category: str
    confidence: str
    reason: str


class DetectCandidatesResponse(BaseModel):
    candidates: list[DetectCandidate]


class MigrateToInsuranceRequest(BaseModel):
    insurer: str
    policy_number: Optional[str] = None
    category_name: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("insurer")
    @classmethod
    def insurer_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("insurer must not be empty")
        return v.strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_insurance_or_404(
    bucket_id: str, insurance_id: str, db: aiosqlite.Connection
) -> dict:
    async with db.execute(
        """
        SELECT i.id, i.bucket_id, i.name, i.insurer, i.policy_number,
               i.recurring_interval, i.recurring_date, i.end_date,
               i.amount, i.currency, i.notes,
               i.category_id, c.name AS category_name,
               i.owner_id, o.name AS owner_name,
               i.created_at, i.updated_at
        FROM insurances i
        LEFT JOIN categories c ON i.category_id = c.id
        LEFT JOIN owners o ON i.owner_id = o.id
        WHERE i.id = ? AND i.bucket_id = ?
        """,
        (insurance_id, bucket_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Insurance not found")
    return dict(row)


async def _get_attachments(insurance_id: str, db: aiosqlite.Connection) -> list[dict]:
    async with db.execute(
        """
        SELECT id, filename, content_type, size_bytes, uploaded_at
        FROM insurance_attachments
        WHERE insurance_id = ?
        ORDER BY uploaded_at
        """,
        (insurance_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def _get_attachment_or_404(
    insurance_id: str, attachment_id: str, db: aiosqlite.Connection
) -> dict:
    async with db.execute(
        """
        SELECT id, insurance_id, filename, content_type, size_bytes, storage_path, uploaded_at
        FROM insurance_attachments
        WHERE id = ? AND insurance_id = ?
        """,
        (attachment_id, insurance_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return dict(row)


# ---------------------------------------------------------------------------
# Routes — insurances
# ---------------------------------------------------------------------------


@router.get(
    "/api/buckets/{bucket_id}/insurances",
    response_model=list[InsuranceResponse],
)
async def list_insurances(
    bucket_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[InsuranceResponse]:
    await _get_bucket_or_404(bucket_id, db)
    await _check_bucket_access(bucket_id, user, db)

    async with db.execute(
        """
        SELECT i.id, i.bucket_id, i.name, i.insurer, i.policy_number,
               i.recurring_interval, i.recurring_date, i.end_date,
               i.amount, i.currency, i.notes,
               c.name AS category_name,
               o.name AS owner_name,
               i.created_at, i.updated_at
        FROM insurances i
        LEFT JOIN categories c ON i.category_id = c.id
        LEFT JOIN owners o ON i.owner_id = o.id
        WHERE i.bucket_id = ?
        ORDER BY i.name
        """,
        (bucket_id,),
    ) as cur:
        rows = [dict(r) for r in await cur.fetchall()]

    # Fetch attachments for every insurance in one query, then group in Python
    # instead of issuing one query per insurance.
    attachments_by_insurance: dict[str, list[dict]] = {}
    if rows:
        async with db.execute(
            """
            SELECT a.id, a.insurance_id, a.filename, a.content_type, a.size_bytes, a.uploaded_at
            FROM insurance_attachments a
            JOIN insurances i ON a.insurance_id = i.id
            WHERE i.bucket_id = ?
            ORDER BY a.uploaded_at
            """,
            (bucket_id,),
        ) as cur:
            for a in await cur.fetchall():
                attachments_by_insurance.setdefault(a["insurance_id"], []).append(dict(a))

    return [
        InsuranceResponse(**r, attachments=attachments_by_insurance.get(r["id"], []))
        for r in rows
    ]


@router.post(
    "/api/buckets/{bucket_id}/insurances",
    response_model=InsuranceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_insurance(
    bucket_id: str,
    body: InsuranceCreate,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> InsuranceResponse:
    await _get_bucket_or_404(bucket_id, db)
    await _check_bucket_access(bucket_id, user, db)

    category_id = (
        await _get_or_create_category(body.category_name, db)
        if body.category_name
        else None
    )
    owner_id = (
        await _get_or_create_owner(body.owner_name, bucket_id, db)
        if body.owner_name
        else None
    )

    async with db.execute(
        """
        INSERT INTO insurances
            (bucket_id, name, insurer, policy_number, recurring_interval,
             recurring_date, end_date, amount, currency, category_id, owner_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id, bucket_id, name, insurer, policy_number,
                  recurring_interval, recurring_date, end_date,
                  amount, currency, notes, created_at, updated_at
        """,
        (
            bucket_id,
            body.name,
            body.insurer,
            body.policy_number,
            body.recurring_interval,
            body.recurring_date,
            body.end_date,
            body.amount,
            body.currency,
            category_id,
            owner_id,
            body.notes,
        ),
    ) as cur:
        row = await cur.fetchone()
    await db.commit()

    return InsuranceResponse(
        **dict(row),
        category_name=body.category_name,
        owner_name=body.owner_name,
        attachments=[],
    )


@router.get("/api/buckets/{bucket_id}/insurances/export")
async def export_insurances(
    bucket_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> StreamingResponse:
    """
    Export all insurances in *bucket_id* as a CSV download.

    Registered before GET /{insurance_id} so the literal "export" path
    segment is matched first instead of being treated as an insurance_id
    (same pitfall as import_csv.router needing to precede subscriptions.router).
    """
    await _get_bucket_or_404(bucket_id, db)
    await _check_bucket_access(bucket_id, user, db)

    async with db.execute("SELECT name FROM buckets WHERE id = ?", (bucket_id,)) as cur:
        bucket_row = await cur.fetchone()
    bucket_name = bucket_row["name"]

    async with db.execute(
        """
        SELECT i.name,
               i.insurer,
               i.policy_number,
               i.recurring_interval,
               i.recurring_date,
               i.end_date,
               i.amount,
               i.currency,
               c.name AS category,
               i.notes
        FROM insurances i
        LEFT JOIN categories c ON i.category_id = c.id
        WHERE i.bucket_id = ?
        ORDER BY i.name
        """,
        (bucket_id,),
    ) as cur:
        rows = await cur.fetchall()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: (row[k] or "") for k in _EXPORT_COLUMNS})

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"{bucket_name.replace(' ', '_')}_insurances.csv"

    logger.info("CSV export for bucket %s: %d insurance rows", bucket_id, len(rows))

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/api/buckets/{bucket_id}/insurances/{insurance_id}",
    response_model=InsuranceResponse,
)
async def get_insurance(
    bucket_id: str,
    insurance_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> InsuranceResponse:
    await _check_bucket_access(bucket_id, user, db)
    existing = await _get_insurance_or_404(bucket_id, insurance_id, db)
    attachments = await _get_attachments(insurance_id, db)
    return InsuranceResponse(**existing, attachments=attachments)


async def _apply_insurance_update(
    db: aiosqlite.Connection,
    bucket_id: str,
    insurance_id: str,
    body: InsuranceUpdate,
    user: CurrentUser,
) -> None:
    """
    Resolve *body* against the current row, run the ``UPDATE``, and record
    change-history rows — but does NOT commit. Shared by the single-record
    ``PUT`` route and the bulk-update route, which both commit once
    themselves (bulk commits once for the whole batch, not per record).
    """
    existing = await _get_insurance_or_404(bucket_id, insurance_id, db)

    # Fields the client actually sent (present in the JSON body, even if the
    # value is null) — vs. fields simply omitted. A cleared date/category/text
    # field is sent as an explicit null; distinguishing the two is required to
    # tell "clear this field" apart from "leave it alone" (both look like
    # `None` once parsed, since Optional[...] fields default to None either way).
    fields_set = body.model_fields_set

    if "category_name" in fields_set:
        category_id = (
            await _get_or_create_category(body.category_name, db)
            if body.category_name
            else None
        )
    else:
        category_id = existing["category_id"]

    if "owner_name" in fields_set:
        owner_id = (
            await _get_or_create_owner(body.owner_name, bucket_id, db)
            if body.owner_name
            else None
        )
    else:
        owner_id = existing["owner_id"]

    updates = {
        "name": body.name if body.name is not None else existing["name"],
        "insurer": body.insurer if body.insurer is not None else existing["insurer"],
        "policy_number": (
            body.policy_number
            if "policy_number" in fields_set
            else existing.get("policy_number")
        ),
        "recurring_interval": (
            body.recurring_interval
            if body.recurring_interval is not None
            else existing["recurring_interval"]
        ),
        "recurring_date": (
            body.recurring_date
            if "recurring_date" in fields_set
            else existing["recurring_date"]
        ),
        "end_date": (
            body.end_date if "end_date" in fields_set else existing.get("end_date")
        ),
        "amount": body.amount if body.amount is not None else existing["amount"],
        "currency": body.currency if body.currency is not None else existing["currency"],
        "category_id": category_id,
        "owner_id": owner_id,
        "notes": body.notes if "notes" in fields_set else existing.get("notes"),
    }

    # Human-readable version of the same resolved values, for the change
    # history log (the SQL updates above use the internal category_id/owner_id FKs).
    new_display_values = {
        **updates,
        "category_name": (
            body.category_name if "category_name" in fields_set else existing["category_name"]
        ),
        "owner_name": (
            body.owner_name if "owner_name" in fields_set else existing["owner_name"]
        ),
    }

    await db.execute(
        """
        UPDATE insurances
        SET name = :name, insurer = :insurer, policy_number = :policy_number,
            recurring_interval = :recurring_interval,
            recurring_date = :recurring_date, end_date = :end_date,
            amount = :amount, currency = :currency,
            category_id = :category_id, owner_id = :owner_id, notes = :notes
        WHERE id = :id
        """,
        {**updates, "id": insurance_id},
    )
    await record_changes(
        db,
        table="insurance_history",
        id_column="insurance_id",
        entity_id=insurance_id,
        old_values=existing,
        new_values=new_display_values,
        fields=INSURANCE_HISTORY_FIELDS,
        user=user,
    )


@router.put(
    "/api/buckets/{bucket_id}/insurances/{insurance_id}",
    response_model=InsuranceResponse,
)
async def update_insurance(
    bucket_id: str,
    insurance_id: str,
    body: InsuranceUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> InsuranceResponse:
    await _check_bucket_access(bucket_id, user, db)
    await _apply_insurance_update(db, bucket_id, insurance_id, body, user)
    await db.commit()

    refreshed = await _get_insurance_or_404(bucket_id, insurance_id, db)
    attachments = await _get_attachments(insurance_id, db)
    return InsuranceResponse(**refreshed, attachments=attachments)


class BulkInsuranceUpdateRequest(BaseModel):
    ids: list[str]
    update: InsuranceUpdate


class BulkUpdateResult(BaseModel):
    updated: int


@router.patch(
    "/api/buckets/{bucket_id}/insurances/bulk",
    response_model=BulkUpdateResult,
)
async def bulk_update_insurances(
    bucket_id: str,
    body: BulkInsuranceUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> BulkUpdateResult:
    await _check_bucket_access(bucket_id, user, db)
    for insurance_id in body.ids:
        await _apply_insurance_update(db, bucket_id, insurance_id, body.update, user)
    await db.commit()
    return BulkUpdateResult(updated=len(body.ids))


@router.delete(
    "/api/buckets/{bucket_id}/insurances/{insurance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_insurance(
    bucket_id: str,
    insurance_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    await _check_bucket_access(bucket_id, user, db)
    await _get_insurance_or_404(bucket_id, insurance_id, db)

    async with db.execute(
        "SELECT storage_path FROM insurance_attachments WHERE insurance_id = ?",
        (insurance_id,),
    ) as cur:
        storage_paths = [r["storage_path"] for r in await cur.fetchall()]

    # ON DELETE CASCADE removes the insurance_attachments rows; delete the
    # underlying files afterward so a failed unlink doesn't block the DB delete.
    await db.execute("DELETE FROM insurances WHERE id = ?", (insurance_id,))
    await db.commit()

    for path in storage_paths:
        delete_attachment_file(path)


# ---------------------------------------------------------------------------
# Routes — attachments
# ---------------------------------------------------------------------------


@router.post(
    "/api/buckets/{bucket_id}/insurances/{insurance_id}/attachments",
    response_model=AttachmentUploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    bucket_id: str,
    insurance_id: str,
    file: UploadFile,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> AttachmentUploadResult:
    await _check_bucket_access(bucket_id, user, db)
    existing = await _get_insurance_or_404(bucket_id, insurance_id, db)

    storage_path, filename, size_bytes = await save_attachment(insurance_id, file)
    content_type = file.content_type or "application/octet-stream"

    async with db.execute(
        """
        INSERT INTO insurance_attachments
            (insurance_id, filename, content_type, size_bytes, storage_path)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id, filename, content_type, size_bytes, uploaded_at
        """,
        (insurance_id, filename, content_type, size_bytes, storage_path),
    ) as cur:
        row = await cur.fetchone()
    await db.commit()

    suggested_updates = await analyze_attachment_for_updates(
        db,
        storage_path=storage_path,
        filename=filename,
        content_type=content_type,
        existing_fields={
            "name": existing["name"],
            "insurer": existing.get("insurer"),
            "policy_number": existing.get("policy_number"),
            "recurring_interval": existing["recurring_interval"],
            "recurring_date": existing.get("recurring_date"),
            "end_date": existing.get("end_date"),
            "amount": existing["amount"],
            "currency": existing["currency"],
            "category_name": existing.get("category_name"),
            "notes": existing.get("notes"),
        },
        kind="insurance",
    )

    return AttachmentUploadResult(
        attachment=AttachmentResponse(**dict(row)),
        suggested_updates=suggested_updates,
    )


@router.get(
    "/api/buckets/{bucket_id}/insurances/{insurance_id}/attachments/{attachment_id}",
)
async def download_attachment(
    bucket_id: str,
    insurance_id: str,
    attachment_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> FileResponse:
    await _check_bucket_access(bucket_id, user, db)
    await _get_insurance_or_404(bucket_id, insurance_id, db)
    attachment = await _get_attachment_or_404(insurance_id, attachment_id, db)

    file_path = attachments_dir() / attachment["storage_path"]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file missing on disk")

    return FileResponse(
        path=str(file_path),
        media_type=attachment["content_type"],
        filename=attachment["filename"],
    )


@router.delete(
    "/api/buckets/{bucket_id}/insurances/{insurance_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_attachment(
    bucket_id: str,
    insurance_id: str,
    attachment_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    await _check_bucket_access(bucket_id, user, db)
    await _get_insurance_or_404(bucket_id, insurance_id, db)
    attachment = await _get_attachment_or_404(insurance_id, attachment_id, db)

    await db.execute(
        "DELETE FROM insurance_attachments WHERE id = ?", (attachment_id,)
    )
    await db.commit()

    delete_attachment_file(attachment["storage_path"])


@router.get(
    "/api/buckets/{bucket_id}/insurances/{insurance_id}/history",
    response_model=list[HistoryEntryResponse],
)
async def get_insurance_history(
    bucket_id: str,
    insurance_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[dict]:
    await _check_bucket_access(bucket_id, user, db)
    await _get_insurance_or_404(bucket_id, insurance_id, db)
    return await get_history(
        db, table="insurance_history", id_column="insurance_id", entity_id=insurance_id
    )


# ---------------------------------------------------------------------------
# Routes — AI-assisted discovery
# ---------------------------------------------------------------------------


@router.post(
    "/api/buckets/{bucket_id}/insurances/detect-candidates",
    response_model=DetectCandidatesResponse,
)
async def detect_candidates(
    bucket_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> DetectCandidatesResponse:
    """
    Ask the configured AI model which of this bucket's subscriptions look
    like insurance policies. Read-only — nothing is created or changed here;
    the frontend calls migrate_subscription_to_insurance per confirmed item.
    """
    await _get_bucket_or_404(bucket_id, db)
    await _check_bucket_access(bucket_id, user, db)

    config = await resolve_ai_config(db)
    if config is None:
        raise HTTPException(
            status_code=400, detail="AI is not configured. Set it up in Settings."
        )

    async with db.execute(
        """
        SELECT s.id, s.name, p.name AS provider_name,
               s.amount, s.currency, s.recurring_interval,
               c.name AS category_name
        FROM subscriptions s
        LEFT JOIN providers p ON s.provider_id = p.id
        LEFT JOIN categories c ON s.category_id = c.id
        WHERE s.bucket_id = ?
        ORDER BY s.name
        """,
        (bucket_id,),
    ) as cur:
        subscriptions = [dict(r) for r in await cur.fetchall()]

    candidates = await detect_insurance_candidates(subscriptions, config)
    return DetectCandidatesResponse(
        candidates=[DetectCandidate(**c) for c in candidates]
    )


@router.post(
    "/api/buckets/{bucket_id}/subscriptions/{sub_id}/migrate-to-insurance",
    response_model=InsuranceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def migrate_subscription_to_insurance(
    bucket_id: str,
    sub_id: str,
    body: MigrateToInsuranceRequest,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> InsuranceResponse:
    """
    Convert a subscription into an insurance: create the insurance record
    (copying billing fields from the subscription) and delete the original
    subscription, atomically (single commit for both operations).
    """
    await _check_bucket_access(bucket_id, user, db)

    async with db.execute(
        """
        SELECT s.id, s.name, s.recurring_interval, s.recurring_date, s.end_date,
               s.amount, s.currency, c.name AS category_name
        FROM subscriptions s
        LEFT JOIN categories c ON s.category_id = c.id
        WHERE s.id = ? AND s.bucket_id = ?
        """,
        (sub_id, bucket_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub = dict(row)

    category_name = (
        body.category_name if body.category_name is not None else sub.get("category_name")
    )
    category_id = (
        await _get_or_create_category(category_name, db) if category_name else None
    )

    async with db.execute(
        """
        INSERT INTO insurances
            (bucket_id, name, insurer, policy_number, recurring_interval,
             recurring_date, end_date, amount, currency, category_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id, bucket_id, name, insurer, policy_number,
                  recurring_interval, recurring_date, end_date,
                  amount, currency, notes, created_at, updated_at
        """,
        (
            bucket_id,
            sub["name"],
            body.insurer,
            body.policy_number,
            sub["recurring_interval"],
            sub["recurring_date"],
            sub["end_date"],
            sub["amount"],
            sub["currency"],
            category_id,
            body.notes,
        ),
    ) as cur:
        new_row = await cur.fetchone()

    await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
    await db.commit()

    return InsuranceResponse(**dict(new_row), category_name=category_name, attachments=[])
