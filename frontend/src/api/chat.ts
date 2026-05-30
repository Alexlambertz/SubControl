/**
 * Chat API — sends a message and consumes the SSE streaming response.
 *
 * The backend streams newline-delimited text chunks via Server-Sent Events.
 */

import { authHeaders } from './client'
import { silentRefresh, clearSessionTokens } from '../auth/tokenRefresh'

const BASE = '/api'

export interface HistoryMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatMessagePayload {
  message: string
  history?: HistoryMessage[]
  bucket_id?: string
  /** Raw text content of a CSV file attached by the user. */
  csv_content?: string
}

/**
 * Send a chat message and stream the response.
 *
 * @param payload  - The user message and optional bucket context.
 * @param onChunk  - Called with each streamed text chunk.
 * @param onDone   - Called when the stream is complete.
 * @param signal   - AbortSignal to cancel the request.
 */
export async function sendChatMessage(
  payload: ChatMessagePayload,
  onChunk: (text: string) => void,
  onDone: () => void,
  signal?: AbortSignal,
): Promise<void> {
  let res = await fetch(`${BASE}/chat/message`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
    signal,
  })

  if (res.status === 401) {
    const refreshed = await silentRefresh()
    if (!refreshed) {
      clearSessionTokens()
      window.location.href = '/'
      throw new Error('Session expired')
    }
    res = await fetch(`${BASE}/chat/message`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
      signal,
    })
  }

  if (!res.ok) {
    throw new Error(`Chat API error: ${res.status}`)
  }

  const reader = res.body?.getReader()
  if (!reader) {
    onDone()
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Process complete SSE lines
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') {
          onDone()
          return
        }
        try {
          const parsed = JSON.parse(data)
          if (parsed.content) {
            onChunk(parsed.content)
          }
        } catch {
          // plain text chunk
          if (data) onChunk(data)
        }
      }
    }
  }

  onDone()
}
