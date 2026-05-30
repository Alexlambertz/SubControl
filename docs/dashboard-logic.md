# Dashboard Logic

The dashboard (`GET /api/dashboard`) operates in two modes.

## Average Monthly mode (`mode=average`)

Converts every subscription's `amount` to a monthly equivalent using fixed factors:

| Interval | Factor |
|----------|--------|
| daily | × 30 |
| weekly | × 4.33 |
| monthly | × 1 |
| quarterly | ÷ 3 |
| half-year | ÷ 6 |
| yearly | ÷ 12 |

`monthly_amount = amount × factor`

Sums all active subscriptions across all (or a filtered) bucket.

## Real Monthly mode (`mode=real&month=YYYY-MM`)

Only includes subscriptions whose **next due date** falls within the queried month.

**Next due date calculation** (`services/dashboard.py → next_due_date`):

Given `recurring_date` (ISO date of last payment) and `interval`, repeatedly advance by the interval's relativedelta until the result is in the future:

```python
next_date = recurring_date
while next_date <= today:
    next_date += relativedelta(months=1)   # or days=1, weeks=1, etc.
```

If `recurring_date` is null, the subscription is excluded in real mode.

## Response shape

```json
{
  "total_monthly": 54.97,
  "subscriptions": [
    {"name": "Netflix", "monthly_amount": 15.99, "currency": "EUR"},
    ...
  ],
  "by_category": [
    {"category": "Streaming", "total": 25.98},
    ...
  ]
}
```

## Filters

| Query param | Description |
|-------------|-------------|
| `bucket_id` | Restrict to a single bucket |
| `category_id` | Restrict to a single category |
