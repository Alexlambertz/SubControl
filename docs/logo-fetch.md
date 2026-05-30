# Logo Fetch

Subscription logos are fetched asynchronously after a subscription is created or updated.

## Strategy

1. **Derive domain** from provider name: lowercase the first word and append `.com`.
   - `"Netflix"` → `netflix.com`
   - `"Adobe CC"` → `adobe.com`

2. **Try Clearbit Logo API**: `GET https://logo.clearbit.com/{domain}`
   - On HTTP 200 → store the URL in `subscriptions.image_url`

3. **Fallback — Google Favicons**: `https://www.google.com/s2/favicons?domain={domain}&sz=128`
   - Always returns a URL (even for unknown domains); stored as-is

4. **Network error or empty provider** → `image_url` remains `null`

## Async behaviour

Logo fetch is fire-and-forget:

```python
asyncio.create_task(_update_logo(sub_id, provider_name, db_path))
```

The subscription creation/update response is returned immediately. The logo URL is updated in the background. Clients should re-fetch the subscription after a short delay to see the logo.

## Configuration

No configuration required. The Clearbit endpoint is public (rate-limited for high volume; upgrade plan if needed). Google Favicons is unconstrained.
