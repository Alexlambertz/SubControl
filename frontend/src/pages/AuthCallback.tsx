/**
 * OIDC redirect callback handler — /auth/callback
 *
 * Keycloak redirects here after the user logs in.
 *
 * Security model
 * --------------
 * The authorization code + PKCE code_verifier are sent to the backend
 * POST /api/auth/exchange, which appends the client_secret server-side
 * before forwarding to Keycloak. The client_secret never touches the browser.
 *
 * Flow
 * ----
 * 1. Read `code` and `state` from the callback URL.
 * 2. Read the PKCE `code_verifier` (and the original return-to path) from
 *    oidc-client-ts's sessionStorage entry (`oidc.<state>`).
 * 3. POST to /api/auth/exchange — backend completes the token exchange.
 * 4. Store the access token, upsert the user, clean up sessionStorage.
 * 5. Full-page redirect to the original URL the user was trying to reach.
 */

import { useEffect, useState } from 'react'
import { setAccessToken } from '../api/client'
import { usersApi } from '../api/users'

/** Shape of the PKCE state object stored by oidc-client-ts in sessionStorage. */
interface OidcState {
  code_verifier: string
  /** The user-provided state passed to signinRedirect() — our return-to path. */
  state?: unknown
}

export default function AuthCallback() {
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function handle() {
      try {
        const params = new URLSearchParams(window.location.search)
        const code = params.get('code')
        const stateKey = params.get('state')

        if (!code || !stateKey) {
          throw new Error('Missing code or state in callback URL')
        }

        // Retrieve the PKCE code_verifier (and return-to path) that
        // oidc-client-ts stored before redirecting to Keycloak.
        const storedRaw = window.sessionStorage.getItem(`oidc.${stateKey}`)
        if (!storedRaw) {
          throw new Error('OIDC session state not found — please try signing in again')
        }
        const stored = JSON.parse(storedRaw) as OidcState
        const { code_verifier } = stored
        const returnTo =
          typeof stored.state === 'string' && stored.state ? stored.state : '/'

        // Exchange the code via the backend — client_secret is added server-side
        const exchangeResp = await fetch('/api/auth/exchange', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            code,
            code_verifier,
            redirect_uri: `${window.location.origin}/auth/callback`,
          }),
        })

        if (!exchangeResp.ok) {
          const detail = await exchangeResp.text()
          throw new Error(`Token exchange failed (${exchangeResp.status}): ${detail}`)
        }

        const { access_token } = (await exchangeResp.json()) as { access_token: string }

        // Persist token for session restoration on next page load
        window.sessionStorage.setItem('subcontrol.access_token', access_token)
        setAccessToken(access_token)

        // Upsert user in DB and record last_login
        await usersApi.login()

        // Clean up OIDC flow state — no longer needed
        window.sessionStorage.removeItem(`oidc.${stateKey}`)

        // Full page replace so AuthContext re-initialises cleanly
        window.location.replace(returnTo)
      } catch (err) {
        console.error('[AuthCallback] error:', err)
        setError(err instanceof Error ? err.message : 'Authentication failed')
      }
    }

    handle()
  }, [])

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="bg-white rounded-2xl border border-red-200 p-8 max-w-sm text-center shadow">
          <p className="text-red-600 font-medium mb-2">Sign-in failed</p>
          <p className="text-sm text-gray-500 mb-4">{error}</p>
          <button
            onClick={() => window.location.replace('/')}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
          >
            Try again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen items-center justify-center bg-gray-50">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm text-gray-500">Signing in…</p>
      </div>
    </div>
  )
}
