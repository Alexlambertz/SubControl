/**
 * AI Chat page — streaming chat interface with subscription context.
 * Conversation history is sent to the backend with every message so the
 * model has full context. The user can clear the history at any time.
 */

import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, Trash2, Paperclip, X, FileText } from 'lucide-react'
import { sendChatMessage } from '../api/chat'
import type { ChatMessage } from '../types'

const STORAGE_KEY = 'subcontrol_chat_messages'

export default function Chat() {
  const [attachedFile, setAttachedFile] = useState<{ name: string; content: string } | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY)
      return saved ? (JSON.parse(saved) as ChatMessage[]) : []
    } catch {
      return []
    }
  })
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Auto-resize textarea to fit content (min 1 row, max 240px)
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input])

  // Persist history across navigation
  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages))
    } catch {
      // sessionStorage unavailable (e.g. private browsing quota) — ignore
    }
  }, [messages])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleFileSelect = (file: File) => {
    if (!file.name.toLowerCase().endsWith('.csv')) {
      return // silently ignore non-CSV files
    }
    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result as string
      setAttachedFile({ name: file.name, content })
    }
    reader.readAsText(file)
  }

  const send = async () => {
    const text = input.trim()
    if ((!text && !attachedFile) || loading) return

    // Capture completed history before mutating state
    const history = messages
      .filter((m) => m.content) // exclude any empty assistant placeholders
      .map((m) => ({ role: m.role, content: m.content }))

    const csvContent = attachedFile?.content ?? undefined
    const userLabel = text
      ? attachedFile ? `${text}\n📎 ${attachedFile.name}` : text
      : `📎 ${attachedFile!.name}`

    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: userLabel }])
    setMessages((prev) => [...prev, { role: 'assistant', content: '' }])
    setLoading(true)

    abortRef.current = new AbortController()

    try {
      await sendChatMessage(
        { message: text || `Please process the attached CSV file.`, history, csv_content: csvContent },
        (chunk) => {
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last.role === 'assistant') {
              updated[updated.length - 1] = { ...last, content: last.content + chunk }
            }
            return updated
          })
        },
        () => setLoading(false),
        abortRef.current.signal,
      )
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError') {
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last.role === 'assistant' && last.content === '') {
            updated[updated.length - 1] = {
              ...last,
              content: '⚠️ Failed to get a response. Check your AI settings.',
            }
          }
          return updated
        })
        setLoading(false)
      }
    }
  }

  const clear = () => {
    abortRef.current?.abort()
    setMessages([])
    setLoading(false)
    setInput('')
    setAttachedFile(null)
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-3xl">
      {/* Header row — only shown when there are messages */}
      {messages.length > 0 && (
        <div className="flex justify-end mb-2">
          <button
            onClick={clear}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-red-500 transition px-2 py-1 rounded-lg hover:bg-red-50"
          >
            <Trash2 size={13} />
            Clear conversation
          </button>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <Bot size={40} className="mx-auto mb-3 opacity-50" />
            <p className="text-sm">
              Ask me about your subscriptions, request analysis, or add new
              subscriptions by chat.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center shrink-0 mt-1">
                <Bot size={16} className="text-blue-600" />
              </div>
            )}
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-tr-sm'
                  : 'bg-white border border-gray-200 text-gray-800 rounded-tl-sm'
              }`}
            >
              {msg.content || (loading && msg.role === 'assistant' ? '…' : '')}
            </div>
            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center shrink-0 mt-1">
                <User size={16} className="text-gray-600" />
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="bg-white rounded-2xl border border-gray-200 p-3 space-y-2">
        {/* Attached file chip */}
        {attachedFile && (
          <div className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-lg px-3 py-1.5 w-fit max-w-full">
            <FileText size={14} className="text-blue-600 shrink-0" />
            <span className="text-xs text-blue-700 font-medium truncate max-w-[200px]">
              {attachedFile.name}
            </span>
            <button
              onClick={() => setAttachedFile(null)}
              className="text-blue-400 hover:text-blue-600 shrink-0"
            >
              <X size={13} />
            </button>
          </div>
        )}

        <div className="flex items-end gap-2">
          {/* Paperclip / file attach */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
            title="Attach CSV file"
            className="p-2 text-gray-400 hover:text-blue-600 disabled:opacity-40 transition shrink-0"
          >
            <Paperclip size={18} />
          </button>

          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleFileSelect(file)
              e.target.value = ''
            }}
          />

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            placeholder={
              attachedFile
                ? 'Describe what to do with this file, or just press Send…'
                : 'Ask about your subscriptions…'
            }
            rows={1}
            className="flex-1 resize-none text-sm outline-none text-gray-800 placeholder-gray-400 bg-transparent"
            style={{ maxHeight: '240px', overflowY: 'auto' }}
          />

          <button
            onClick={send}
            disabled={(!input.trim() && !attachedFile) || loading}
            className="p-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-40 transition shrink-0"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
