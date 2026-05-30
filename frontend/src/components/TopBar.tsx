/**
 * Top navigation bar — hamburger (mobile), page title, global search, user info.
 */

import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Search, User, LogOut, Menu } from 'lucide-react'

interface Props {
  onMenuToggle: () => void
}

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/buckets': 'Buckets',
  '/subscriptions': 'Subscriptions',
  '/search': 'Search',
  '/users': 'Users',
  '/chat': 'AI Chat',
  '/settings': 'Settings',
}

export default function TopBar({ onMenuToggle }: Props) {
  const { pathname } = useLocation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const inputRef = useRef<HTMLInputElement>(null)

  const title =
    Object.entries(PAGE_TITLES).find(([path]) =>
      path === '/' ? pathname === '/' : pathname.startsWith(path),
    )?.[1] ?? 'SubControl'

  const urlQuery = pathname === '/search' ? (searchParams.get('q') ?? '') : ''
  const [q, setQ] = useState(urlQuery)

  useEffect(() => { setQ(urlQuery) }, [urlQuery])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = q.trim()
    if (trimmed) navigate(`/search?q=${encodeURIComponent(trimmed)}`)
  }

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center gap-3 px-4 md:px-6 shrink-0">
      {/* Hamburger — only visible on mobile */}
      <button
        onClick={onMenuToggle}
        className="lg:hidden p-2 -ml-1 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition"
        aria-label="Open menu"
      >
        <Menu size={20} />
      </button>

      {/* Page title — hidden on very small screens to give search more room */}
      <h1 className="hidden sm:block text-lg font-semibold text-gray-800 shrink-0 w-32 truncate">
        {title}
      </h1>

      {/* Search bar */}
      <form onSubmit={handleSubmit} className="flex-1 max-w-md">
        <div className="relative">
          <Search
            size={15}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
          />
          <input
            ref={inputRef}
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && setQ('')}
            placeholder="Search…"
            className="w-full pl-9 pr-10 py-2 text-sm bg-gray-50 border border-gray-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition placeholder-gray-400"
          />
          <kbd className="absolute right-3 top-1/2 -translate-y-1/2 hidden md:flex items-center gap-0.5 text-[10px] text-gray-400 pointer-events-none">
            <span className="font-sans">⌘K</span>
          </kbd>
        </div>
      </form>

      {/* User info */}
      {user && (
        <div className="flex items-center gap-2 text-sm text-gray-600 shrink-0 ml-auto">
          <User size={16} className="shrink-0" />
          <span className="hidden md:block truncate max-w-[120px]">{user.username}</span>
          {user.is_admin && (
            <span className="hidden sm:block bg-blue-100 text-blue-700 text-xs px-2 py-0.5 rounded-full">
              admin
            </span>
          )}
          <button
            onClick={logout}
            className="p-1.5 text-gray-400 hover:text-red-500 rounded-lg hover:bg-red-50 transition"
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut size={15} />
          </button>
        </div>
      )}
    </header>
  )
}
