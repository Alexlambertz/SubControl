# CSV Import

**Endpoint:** `POST /api/buckets/{bucket_id}/subscriptions/import`

Upload a CSV file to bulk-import subscriptions into a bucket.

## Expected CSV format

```csv
name,provider,recurring_interval,recurring_date,amount,currency,category
Netflix Premium,Netflix,monthly,2024-01-15,15.99,EUR,Streaming
Spotify,Spotify,monthly,,9.99,EUR,Music
GitHub Pro,GitHub,monthly,,4.00,USD,Developer Tools
```

### Column reference

| Column | Required | Notes |
|--------|----------|-------|
| `name` | Yes | Subscription display name |
| `provider` | No | Provider name; created if it doesn't exist |
| `recurring_interval` | Yes | `daily`, `weekly`, `monthly`, `quarterly`, `half-year`, `yearly` |
| `recurring_date` | No | ISO date `YYYY-MM-DD` — last payment date |
| `amount` | Yes | Numeric, e.g. `9.99` |
| `currency` | No | 3-char ISO 4217; defaults to `EUR` |
| `category` | No | Category name; created if it doesn't exist |

- File encoding: UTF-8 (BOM-tolerant) or latin-1 fallback
- `Content-Type: multipart/form-data`, field name: `file`

## Response

```json
{
  "imported": 2,
  "failed": [
    {"row": 2, "error": "Invalid interval: 'biweekly'"}
  ]
}
```

- `imported`: number of successfully created subscriptions
- `failed`: list of per-row errors (0-indexed row numbers, excluding header)

Rows that fail validation are skipped; the remainder are still imported.

## Behaviour on missing bucket

Returns `404` if `bucket_id` does not exist.
