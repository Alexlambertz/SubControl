/**
 * OIDC redirect callback handler — /auth/callback
 *
 * Keycloak redirects here after the user logs in.
 * This page completes the PKCE code exchange, stores the token,
 * upserts the user in the database, then redirects to the original page.
 */

import { useEffect, useState } from 'react'
import { UserManager, WebStorageStateStore } from 'oidc-client-ts'
import { setAccessToken } from '../api/client'
import { usersApi } from '../api/users'

export default function AuthCallback() {
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function handle() {
      try {
        // Fetch the same config the AuthContext uses
        const resp = await fetch('/api/config')
        if (!resp.ok) throw new Error(`/api/config returned ${resp.status}`)
        const config = await resp.json() as {
          oidc_issuer_url: string
          oidc_client_id: string
        }

        // Use the same UserManager settings as AuthContext so the stored
        // PKCE state (code_verifier etc.) in sessionStorage is found.
        const um = new UserManager({
          authority: config.oidc_issuer_url,
          client_id: config.oidc_client_id,
          redirect_uri: `${window.location.origin}/auth/callback`,
          response_type: 'code',
          scope: 'openid profile email',
          userStore: new WebStorageStateStore({ store: window.sessionStorage }),
        })

        const oidcUser = await um.signinRedirectCallback()
        setAccessToken(oidcUser.access_token)

        // Upsert user in DB and record last_login
        await usersApi.login()

        // Return to the page the user was trying to reach before login
        const returnTo = (typeof oidcUser.state === 'string' && oidcUser.state)
          ? oidcUser.state
          : '/'

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
