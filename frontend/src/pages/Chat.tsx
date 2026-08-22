/**
 * AI Chat page — streaming chat interface with subscription and insurance context.
 *
 * Conversations are persisted server-side per user. The right-hand sidebar
 * lists recent conversations so they can be reopened; "New chat" starts a
 * fresh one. The in-flight `history` sent with each message is still built
 * from local `messages` state (unchanged), independent of server persistence.
 */

import { useState, useRef, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNowStrict } from 'date-fns'
import { Send, Bot, User, Trash2, Paperclip, X, FileText, Plus, MessageSquare } from 'lucide-react'
import { sendChatMessage, chatConversationsApi } from '../api/chat'
import ConfirmDialog from '../components/ConfirmDialog'
import type { ChatMessage, ChatConversationSummary } from '../types'

// SQLite's datetime('now') yields "YYYY-MM-DD HH:MM:SS" in UTC with a space
// separator, not a Date-parseable ISO string — normalize it.
function parseSqliteDate(value: string): Date {
  return new Date(value.includes('T') ? value : `${value.replace(' ', 'T')}Z`)
}

export default function Chat() {
  const qc = useQueryClient()

  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [attachedFile, setAttachedFile] = useState<{ name: string; content: string } | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<ChatConversationSummary | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const { data: conversations = [] } = useQuery({
    queryKey: ['chatConversations'],
    queryFn: chatConversationsApi.list,
  })

  // Auto-resize textarea to fit content (min 1 row, max 240px)
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: loading ? 'auto' : 'smooth' })
  }, [messages, loading])

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
        {
          message: text || `Please process the attached CSV file.`,
          history,
          csv_content: csvContent,
          conversation_id: activeConversationId ?? undefined,
        },
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
        () => {
          setLoading(false)
          qc.invalidateQueries({ queryKey: ['chatConversations'] })
        },
        abortRef.current.signal,
        (id) => {
          setActiveConversationId(id)
          qc.invalidateQueries({ queryKey: ['chatConversations'] })
        },
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

  const startNewChat = () => {
    abortRef.current?.abort()
    setActiveConversationId(null)
    setMessages([])
    setLoading(false)
    setInput('')
    setAttachedFile(null)
  }

  const openConversation = async (id: string) => {
    if (id === activeConversationId) return
    abortRef.current?.abort()
    setLoading(false)
    setInput('')
    setAttachedFile(null)
    setActiveConversationId(id)
    setMessages([])
    try {
      const detail = await chatConversationsApi.get(id)
      setMessages(detail.messages.map((m) => ({ role: m.role, content: m.content })))
    } catch {
      setMessages([{ role: 'assistant', content: '⚠️ Failed to load this conversation.' }])
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    const id = deleteTarget.id
    setDeleteTarget(null)
    await chatConversationsApi.delete(id)
    qc.invalidateQueries({ queryKey: ['chatConversations'] })
    if (id === activeConversationId) startNewChat()
  }

  return (
    <div className="flex gap-4 h-[calc(100vh-8rem)]">
      {/* Chat column */}
      <div className="flex flex-col flex-1 min-w-0 max-w-3xl">
        {/* Header row — only shown when there are messages */}
        {messages.length > 0 && (
          <div className="flex justify-end mb-2">
            <button
              onClick={startNewChat}
              className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-blue-600 transition px-2 py-1 rounded-lg hover:bg-blue-50"
            >
              <Plus size={13} />
              New chat
            </button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto space-y-4 pb-4" data-testid="chat-thread">
          {messages.length === 0 && (
            <div className="text-center py-16 text-gray-400">
              <Bot size={40} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm">
                Ask me about your subscriptions and insurance policies, request
                analysis, or add new ones by chat.
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
              aria-label="Send"
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Recent conversations sidebar */}
      <div className="hidden md:flex flex-col w-64 shrink-0 border-l border-gray-100 pl-4">
        <button
          onClick={startNewChat}
          className="flex items-center justify-center gap-1.5 text-sm font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-xl px-3 py-2 mb-3 transition"
        >
          <Plus size={15} />
          New chat
        </button>

        <div className="flex-1 overflow-y-auto space-y-1">
          {conversations.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-8">
              No conversations yet.
            </p>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => openConversation(c.id)}
              className={`group flex items-start gap-2 px-3 py-2 rounded-lg cursor-pointer transition ${
                c.id === activeConversationId
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <MessageSquare size={14} className="shrink-0 mt-0.5 opacity-60" />
              <div className="min-w-0 flex-1">
                <p className="text-sm truncate">{c.title}</p>
                <p className="text-xs text-gray-400">
                  {formatDistanceToNowStrict(parseSqliteDate(c.updated_at), { addSuffix: true })}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setDeleteTarget(c)
                }}
                className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition shrink-0"
                title="Delete conversation"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {deleteTarget && (
        <ConfirmDialog
          title="Delete conversation"
          message={`Delete "${deleteTarget.title}"? This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}
