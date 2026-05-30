/**
 * Token refresh utilities.
 *
 * Provides two mechanisms to keep the session alive:
 *
 * 1. Proactive: scheduleTokenRefresh() sets a timer that silently refreshes
 *    the access token 60 s before it expires, so the user never sees a 401.
 *
 * 2. Reactive: silentRefresh() is also called by the API client when a 401
 *    is encountered mid-session, as a safety net in case the timer missed.
 *
 * Both mechanisms call POST /api/auth/refresh, which adds the client_secret
 * server-side (never stored in the browser).
 */

import { setAccessToken } from '../api/client'

let _refreshTimer: ReturnType<typeof setTimeout> | null = null

/** Deduplicates concurrent refresh attempts. */
let _refreshPromise: Promise<boolean> | null = null

// ---------------------------------------------------------------------------
// Proactive scheduling
// ---------------------------------------------------------------------------

/**
 * Schedule a silent token refresh `expiresIn` seconds from now, with a
 * 60-second safety margin.  Call this whenever a new access token is issued.
 */
export function scheduleTokenRefresh(expiresIn: number): void {
  if (_refreshTimer) clearTimeout(_refreshTimer)
  // Refresh 60 s before expiry; at least 10 s from now to avoid busy loops
  const delayMs = Math.max(10_000, (expiresIn - 60) * 1000)
  _refreshTimer = setTimeout(() => {
    silentRefresh().then((ok) => {
      if (!ok) {
        // Refresh failed — redirect to home so AuthContext triggers re-login
        clearSessionTokens()
        window.location.href = '/'
      }
    })
  }, delayMs)
}

// ---------------------------------------------------------------------------
// Silent refresh
// ---------------------------------------------------------------------------

/**
 * Exchange the stored refresh token for a new access token.
 *
 * Returns true on success, false if the refresh token is missing or rejected.
 * Safe to call concurrently — concurrent calls share a single in-flight request.
 */
export async function silentRefresh(): Promise<boolean> {
  if (_refreshPromise) return _refreshPromise

  _refreshPromise = _doRefresh().finally(() => {
    _refreshPromise = null
  })
  return _refreshPromise
}

async function _doRefresh(): Promise<boolean> {
  const refreshToken = window.sessionStorage.getItem('subcontrol.refresh_token')
  if (!refreshToken) return false

  try {
    const resp = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })

    if (!resp.ok) {
      clearSessionTokens()
      return false
    }

    const { access_token, refresh_token: newRT, expires_in } = await resp.json() as {
      access_token: string
      refresh_token?: string
      expires_in: number
    }

    setAccessToken(access_token)
    window.sessionStorage.setItem('subcontrol.access_token', access_token)
    window.sessionStorage.setItem('subcontrol.token_expires_at', String(Date.now() + expires_in * 1000))
    if (newRT) window.sessionStorage.setItem('subcontrol.refresh_token', newRT)

    scheduleTokenRefresh(expires_in)
    return true
  } catch {
    clearSessionTokens()
    return false
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function clearSessionTokens(): void {
  if (_refreshTimer) { clearTimeout(_refreshTimer); _refreshTimer = null }
  window.sessionStorage.removeItem('subcontrol.access_token')
  window.sessionStorage.removeItem('subcontrol.refresh_token')
  window.sessionStorage.removeItem('subcontrol.token_expires_at')
  setAccessToken(null)
}
