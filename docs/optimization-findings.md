# Optimization Findings

Scan of the current implementation (backend + frontend) as of `e917913`, looking for
performance, network, and resource-usage issues. Not a full audit — findings are ranked
roughly by impact within each half. Nothing here has been changed yet.

## Backend

### 1. No database indexes exist anywhere (highest impact)
`backend/migrations/*.sql` contain zero `CREATE INDEX` statements. `subscriptions.bucket_id`
is the primary filter column for nearly every query — `routers/subscriptions.py:145,235`,
`routers/dashboard.py:107,193`, `routers/import_csv.py:116,172`, `services/logo_fetch.py:120`,
`routers/import_external.py:143` — so every one of these does a full table scan today.
`subscriptions.provider_id`/`category_id` (used in every `LEFT JOIN`) are unindexed too.
**Fix:** new migration adding `CREATE INDEX idx_subscriptions_bucket_id ON subscriptions(bucket_id)`
(+ provider_id/category_id indexes, + an index on `user_buckets(bucket_id)` for the reverse
lookup used on bucket deletion).

### 2. `get_db()` opens a new connection and does a blocking mkdir on every request
`backend/database.py:41-56`. Every request re-derives the DB path, calls the **synchronous**
`Path(db_path).parent.mkdir(...)` directly on the event loop (not off-loaded), opens a fresh
`aiosqlite.connect()`, and re-issues `PRAGMA foreign_keys = ON` — no pooling/reuse at all.
**Fix:** open one long-lived connection (or small pool) in the FastAPI `lifespan`, call `mkdir`
once at startup instead of per-request.

### 3. CSV/Wallos import: N+1 lookups + row-by-row inserts
`backend/services/csv_import.py:57-83,184-185` and `backend/services/wallos_import.py:84-110,311-312`.
Each imported row triggers up to 2 extra provider/category `SELECT`s (+ possible `INSERT`) and
its own `INSERT INTO subscriptions` — none batched. A few-hundred-row import means hundreds of
unnecessary round trips.
**Fix:** pre-fetch all providers/categories into an in-memory dict once, `executemany` for any
missing ones, then `executemany` the subscription inserts.

### 4. `logo_fetch.py`: sequential HTTP calls + new client + new DB connection per row
`backend/services/logo_fetch.py:60-87,139-155`. `fetch_logo_url` creates a brand-new
`httpx.AsyncClient` on every call; `refresh_logos_for_bucket` awaits fetches one at a time and
opens/closes a fresh SQLite connection per `UPDATE`. Same pattern in
`routers/subscriptions.py:200-205`, `routers/import_external.py:140-155`,
`services/ai_chat.py:484-493`. A 50-subscription bucket serializes 50 external round-trips with
no connection reuse.
**Fix:** reuse one `httpx.AsyncClient` across a batch, one DB connection with batched/committed
updates, bound concurrency with `asyncio.gather` + `Semaphore`.

### 5. `build_yearly_totals` steps dates one interval at a time
`backend/services/dashboard.py:229-247` via `any_occurrence_in_month`/`due_date_in_month`
(`148-157`, `195-203`). For `daily`/`weekly` intervals with an old anchor date, the loop
(`while due < target_start: due += delta`) can run hundreds/thousands of iterations per
(subscription × month). Worst case O(n_subs × 12 × days_since_anchor).
**Fix:** closed-form arithmetic — `(target_start - anchor).days // interval_days` for date-based
intervals, direct `relativedelta` month-diff for month-based ones — making each lookup O(1).

### 6. `update_subscription` re-queries data it already has
`backend/routers/subscriptions.py:338-342,349-353`. When `provider_name`/`category_name` aren't
in the PATCH body, it issues fresh `SELECT provider_id`/`SELECT category_id` queries even though
`existing` (fetched at line 330) already hit the same row — it just doesn't select those raw
columns.
**Fix:** add `s.provider_id, s.category_id` to `_get_sub_or_404`'s SELECT and reuse them.

### 7. Substring search can never use an index
`backend/routers/search.py:46,56-60,97-100`. Leading-wildcard `LIKE '%q%' COLLATE NOCASE` on
`subscriptions.name`/`providers.name`/`categories.name` forces a full scan regardless of #1.
**Fix:** for scale, add an SQLite FTS5 virtual table instead of `LIKE`; flagged as a scaling risk
today rather than an urgent fix.

### 8. Unbounded list/export queries
`backend/routers/subscriptions.py:224-240`, `backend/routers/import_csv.py:159-177`,
`backend/routers/providers_categories.py:58,95`. No `LIMIT`/pagination — fine at current scale,
but grows unbounded with usage and compounds with #1.
**Fix:** add pagination or a sane cap, matching what `search` already does.

### 9. No caching of resolved logo URLs
`backend/services/logo_fetch.py:60-87`. Every subscription hits Clearbit fresh even when many
subscriptions across buckets share a provider (e.g. "Netflix").
**Fix:** cache `provider_name → logo_url` (in-memory TTL, or check for an existing
`image_url` on another subscription with the same `provider_id` before calling out).

## Frontend

### 1. Provider/category autocomplete is silently broken — wasted failing requests (highest impact, also a correctness bug)
`frontend/src/pages/Subscriptions/SubscriptionForm.tsx:16,20`. `get()` already prefixes every
path with `/api` (`frontend/src/api/client.ts:17,68`), but these two calls pass
`/api/providers`/`/api/categories`, producing requests to `/api/api/providers` /
`/api/api/categories`. Confirmed no other API module double-prefixes this way. Every time the
subscription form opens, two requests fire and fail, and the failure is swallowed
(`Array.isArray(data) ? data : []`), silently leaving the autocomplete empty.
**Fix:** change to `get('/providers')` / `get('/categories')`.

### 2. No route-level code splitting
`frontend/src/router.tsx:9-17`. All pages are statically imported, so `recharts` (used only by
`Dashboard.tsx`) and admin-only pages (`Users`, `Settings`) ship in the initial bundle for every
user.
**Fix:** `React.lazy()` + `<Suspense>` for `Dashboard`, `UserList`, `Settings`,
`ImportHub`/`WallosImport` at minimum.

### 3. Duplicate-detection check is O(subs × duplicateSubs), recomputed every render
`frontend/src/pages/Subscriptions/SubscriptionList.tsx:249-253`. `isDuplicateCandidate` does a
nested `.some()` scan per row, inline in the render body (not memoized), rerunning on every
render of the list — not just when `subs`/`duplicateGroups` change. List is also unvirtualized.
**Fix:** precompute a `Set<string>` of duplicate IDs via `useMemo` alongside the existing
`duplicateGroups` memo (line 103); consider windowing if buckets grow large.

### 4. Chat streaming does a full sessionStorage write + smooth-scroll per chunk
`frontend/src/pages/Chat.tsx:44-55`. Both effects fire on every `messages` update, and `send()`
calls `setMessages` on every SSE chunk — so a long streamed response triggers dozens/hundreds of
`JSON.stringify` + `sessionStorage.setItem` calls and repeated smooth-scroll animation.
**Fix:** throttle/debounce the persistence write (e.g. only on stream completion), use
`behavior: 'auto'` or throttle scrolling during active streaming.

### 5. `AuthContext` value and callbacks recreated every render
`frontend/src/auth/AuthContext.tsx:190-202`. `login`/`logout` are new closures and the `value`
object is a new reference every render, so every consumer (Sidebar, TopBar, router guards, Chat,
UserList, …) re-renders even when `user`/`isLoading` haven't changed.
**Fix:** wrap `login`/`logout` in `useCallback`, wrap the provider `value` in
`useMemo([user, isLoading])`.

### 6. Oversized PWA icon assets
`frontend/public/icon-512.png` (252 KB), `icon-maskable-512.png` (176 KB) — large for flat
512×512 icons, typically compressible to well under 50-80 KB. Fetched during PWA
install/manifest prefetch. `icon-192.png`/`icon-maskable-192.png` are reasonable by comparison.
**Fix:** recompress with pngquant/oxipng, or serve as WebP.

### 7. `SortableTable` sorts an unmemoized array copy every render
`frontend/src/components/SortableTable.tsx:52-58`. `[...data].sort(...)` clones/sorts
unconditionally. Note: currently unused anywhere in the app (no importers found) — latent issue
worth fixing before it's wired into a page with real data.
**Fix:** `useMemo(() => [...data].sort(...), [data, sortKey, sortDir])`.

### 8. `Search.tsx` recomputes filters/totals every render
`frontend/src/pages/Search.tsx:62-77`. Filtering into `buckets`/`subscriptions` and reducing
`totalMonthly` run on every render, including ones triggered by unrelated state (e.g.
`editTarget`). Minor at typical result-set sizes.
**Fix:** wrap in `useMemo([data])`.

## Suggested next step

Highest-value, lowest-risk fixes to start with: backend #1 (indexes) and #6 (redundant query),
frontend #1 (broken autocomplete — this is a real bug, not just an optimization) and #5
(AuthContext memoization). These are small, isolated changes with no behavioral risk. The
import-loop batching (backend #3) and dashboard date-arithmetic rewrite (backend #5) are higher
effort but worth doing before either the subscription count or the daily/weekly-interval date
ranges grow significantly.
