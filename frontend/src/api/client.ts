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

const BASE = '/api'

/** Retrieve stored auth token (set by AuthContext after login). */
let _accessToken: string | null = null

export function setAccessToken(token: string | null): void {
  _accessToken = token
}

function authHeaders(): Record<string, string> {
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

export async function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  let url = `${BASE}${path}`
  if (params) {
    const q = Object.entries(params)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join('&')
    if (q) url += `?${q}`
  }
  const res = await fetch(url, { headers: authHeaders() })
  return handleResponse<T>(res)
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: authHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(res)
}

export async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

export async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

export async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  return handleResponse<T>(res)
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
  return handleResponse<T>(res)
}
