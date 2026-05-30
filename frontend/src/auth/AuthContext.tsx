/**
 * AuthContext — OIDC-backed authentication for SubControl.
 *
 * Startup sequence
 * ----------------
 * 1. Fetch /api/config to discover dev_mode + OIDC settings.
 * 2. DEV_MODE=true  → call /api/auth/me directly (no token needed).
 * 3. DEV_MODE=false → use oidc-client-ts:
 *    a. If already at /auth/callback — let the callback page handle it.
 *    b. Restore existing session from sessionStorage (getUser).
 *    c. If valid token found  → set Bearer header, call /api/auth/login.
 *    d. If no/expired session → signinRedirect() to Keycloak.
 *
 * Token lifecycle
 * ---------------
 * The access token is stored in sessionStorage by oidc-client-ts and
 * injected into every API request via setAccessToken() from api/client.ts.
 * When the token expires the user is redirected to Keycloak for re-login.
 */

import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { UserManager, WebStorageStateStore } from 'oidc-client-ts'
import { setAccessToken } from '../api/client'
import { usersApi } from '../api/users'
import type { User } from '../types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AppConfig {
  dev_mode: boolean
  oidc_issuer_url: string
  oidc_client_id: string
}

interface AuthContextValue {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: () => void
  logout: () => void
}

// ---------------------------------------------------------------------------
// Singleton UserManager — created once and reused across the session
// ---------------------------------------------------------------------------

let _userManager: UserManager | null = null

/** Exposed so the AuthCallback page can reuse the same instance. */
export function getUserManager(): UserManager | null {
  return _userManager
}

function buildUserManager(config: AppConfig): UserManager {
  // The SPA is an OAuth 2.0 public client — PKCE replaces the client secret.
  // oidc-client-ts generates a code_verifier/code_challenge automatically.
  _userManager = new UserManager({
    authority: config.oidc_issuer_url,
    client_id: config.oidc_client_id,
    redirect_uri: `${window.location.origin}/auth/callback`,
    post_logout_redirect_uri: `${window.location.origin}/`,
    response_type: 'code',
    scope: 'openid profile email',
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    // Silent renew requires a dedicated /silent-renew.html; disabled for now.
    automaticSilentRenew: false,
  })
  return _userManager
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  login: () => {},
  logout: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function init() {
      try {
        // 1. Discover runtime config (unauthenticated endpoint)
        const resp = await fetch('/api/config')
        if (!resp.ok) throw new Error(`/api/config returned ${resp.status}`)
        const config: AppConfig = await resp.json()

        // 2. DEV_MODE — backend accepts requests without a token
        if (config.dev_mode) {
          const u = await usersApi.me()
          if (!cancelled) { setUser(u); setIsLoading(false) }
          return
        }

        // 3. Production OIDC
        //    If we're already at the callback URL let that page handle things.
        if (window.location.pathname === '/auth/callback') {
          if (!cancelled) setIsLoading(false)
          return
        }

        const um = buildUserManager(config)

        // Try to restore an existing (non-expired) session
        const oidcUser = await um.getUser()
        if (oidcUser && !oidcUser.expired) {
          setAccessToken(oidcUser.access_token)
          try {
            const u = await usersApi.login()
            if (!cancelled) { setUser(u); setIsLoading(false) }
          } catch {
            // Token might be stale — force re-login
            setAccessToken(null)
            await um.removeUser()
            await um.signinRedirect({ state: window.location.pathname + window.location.search })
          }
          return
        }

        // No valid session → redirect to Keycloak (browser navigates away)
        await um.signinRedirect({
          state: window.location.pathname + window.location.search,
        })
        // Never reached after redirect
      } catch (err) {
        console.error('[Auth] init error:', err)
        if (!cancelled) setIsLoading(false)
      }
    }

    init()
    return () => { cancelled = true }
  }, [])

  const login = async () => {
    if (_userManager) await _userManager.signinRedirect()
  }

  const logout = async () => {
    setUser(null)
    setAccessToken(null)
    if (_userManager) {
      await _userManager.removeUser()
      await _userManager.signoutRedirect()
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: user !== null,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext)
}
