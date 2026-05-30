/**
 * Base API client.
 *
 * All requests are prefixed with /api.  In development, Vite's proxy
 * forwards them to the FastAPI backend.  In production they are served
 * by the same origin.
 *
 * Authentication: the JWT from the OIDC context is injected as a
 * Bearer token by getAuthHeaders().  In DEV_MODE the backend accepts
 * unauthenticated requests so the token may be absent.
 */

// Note: tokenRefresh imports setAccessToken from this module — the circular
// dependency is safe because both sides use the imports only inside functions.
import { silentRefresh, clearSessionTokens } from '../auth/tokenRefresh'

const BASE = '/api'

/** Retrieve stored auth token (set by AuthContext after login). */
let _accessToken: string | null = null

export function setAccessToken(token: string | null): void {
  _accessToken = token
}

export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (_accessToken) {
    headers['Authorization'] = `Bearer ${_accessToken}`
  }
  return headers
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      // ignore parse error
    }
    throw new Error(`API ${res.status}: ${detail}`)
  }
  if (res.status === 204) return undefined as unknown as T
  return res.json() as Promise<T>
}

/**
 * Fetch wrapper that retries once after a silent token refresh on 401.
 * Redirects to / (triggering re-login) if the refresh also fails.
 */
async function fetchWithAuth(url: string, init: RequestInit): Promise<Response> {
  const res = await fetch(url, { ...init, headers: { ...authHeaders(), ...(init.headers as Record<string, string> ?? {}) } })
  if (res.status !== 401) return res

  const refreshed = await silentRefresh()
  if (!refreshed) {
    clearSessionTokens()
    window.location.href = '/'
    throw new Error('Session expired')
  }
  // Retry once with the new token
  return fetch(url, { ...init, headers: { ...authHeaders(), ...(init.headers as Record<string, string> ?? {}) } })
}

export async function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  let url = `${BASE}${path}`
  if (params) {
    const q = Object.entries(params)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join('&')
    if (q) url += `?${q}`
  }
  const res = await fetchWithAuth(url, {})
  return handleResponse<T>(res)
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetchWithAuth(`${BASE}${path}`, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(res)
}

export async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetchWithAuth(`${BASE}${path}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

export async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetchWithAuth(`${BASE}${path}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

export async function del<T>(path: string): Promise<T> {
  const res = await fetchWithAuth(`${BASE}${path}`, { method: 'DELETE' })
  return handleResponse<T>(res)
}

/** GET a binary response (e.g. CSV download) with the Bearer token attached. */
export async function getBlob(path: string): Promise<Blob> {
  const res = await fetchWithAuth(`${BASE}${path}`, {})
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* ignore */ }
    throw new Error(`API ${res.status}: ${detail}`)
  }
  return res.blob()
}

export async function postFormData<T>(path: string, formData: FormData): Promise<T> {
  const headers: Record<string, string> = {}
  if (_accessToken) {
    headers['Authorization'] = `Bearer ${_accessToken}`
  }
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers,
    body: formData,
  })
  // Retry on 401 for form data too
  if (res.status === 401) {
    const refreshed = await silentRefresh()
    if (!refreshed) { clearSessionTokens(); window.location.href = '/'; throw new Error('Session expired') }
    const retryHeaders: Record<string, string> = {}
    if (_accessToken) retryHeaders['Authorization'] = `Bearer ${_accessToken}`
    const retry = await fetch(`${BASE}${path}`, { method: 'POST', headers: retryHeaders, body: formData })
    return handleResponse<T>(retry)
  }
  return handleResponse<T>(res)
}
