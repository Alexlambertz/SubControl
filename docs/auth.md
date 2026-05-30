# Authentication

## Development mode

Set `DEV_MODE=true` (default). All authentication is bypassed.

`backend/dependencies.py` injects a hardcoded admin user:
```python
_DEV_USER = CurrentUser(
    id="00000000000000000000000000000001",
    username="dev_admin",
    is_admin=True,
)
```

No token is required. Every request is treated as this admin user.

## Production mode (`DEV_MODE=false`)

**PKCE flow with Keycloak:**

1. Frontend: `oidc-client-ts` library initiates an authorization code + PKCE flow.
2. Keycloak issues a JWT access token after successful login.
3. Frontend stores the token and includes it as `Authorization: Bearer <token>` on every API request.
4. Backend `get_current_user` dependency:
   - Extracts the Bearer token.
   - Fetches Keycloak's JWKS endpoint (`OIDC_ISSUER_URL + /.well-known/jwks.json`).
   - Validates signature, expiry, and issuer using `python-jose`.
   - Extracts `sub` as `username`.
5. **First login auto-promotion**: the very first user to log in is promoted to admin (`is_admin=1`).

## Admin guard

`require_admin` dependency raises `403` if `current_user.is_admin` is `False`.

Used on: DELETE /buckets, /users/* routes, /settings/* routes, bucket user assignment.

## Environment variables

| Variable | Description |
|----------|-------------|
| `DEV_MODE` | `true` to skip auth (default) |
| `SECRET_KEY` | JWT signing secret (production) |
| `OIDC_ISSUER_URL` | Keycloak realm URL, e.g. `http://localhost:8080/realms/subcontrol` |
| `OIDC_CLIENT_ID` | Keycloak client ID (default `subcontrol`) |
| `OIDC_AUDIENCE` | Optional JWT audience claim |
