/**
 * Application sidebar with navigation links.
 *
 * On mobile (< lg) it slides in as an off-canvas drawer controlled by the
 * parent Layout.  On lg+ it is always visible as a fixed-width column.
 * Admin-only links (Users, Settings) are hidden for non-admin users.
 */

import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  FolderOpen,
  Users,
  MessageSquare,
  Settings,
  Upload,
  X,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../auth/AuthContext'
import { bucketsApi } from '../api/buckets'
import { version } from '../../package.json'

interface Props {
  isOpen: boolean
  onClose: () => void
}

const allLinks = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, adminOnly: false },
  { to: '/buckets', label: 'Buckets', icon: FolderOpen, adminOnly: false },
  { to: '/import', label: 'Import', icon: Upload, adminOnly: false },
  { to: '/chat', label: 'AI Chat', icon: MessageSquare, adminOnly: false },
  { to: '/users', label: 'Users', icon: Users, adminOnly: true },
  { to: '/settings', label: 'Settings', icon: Settings, adminOnly: true },
]

export default function Sidebar({ isOpen, onClose }: Props) {
  const { user } = useAuth()
  const isAdmin = user?.is_admin ?? false
  const links = allLinks.filter((l) => !l.adminOnly || isAdmin)

  // Shown inline under the "Buckets" link for one-click access to a bucket.
  const { data: buckets = [] } = useQuery({
    queryKey: ['buckets'],
    queryFn: bucketsApi.list,
  })

  return (
    <nav
      className={clsx(
        // Base styles
        'fixed inset-y-0 left-0 z-30 w-56 bg-white border-r border-gray-200 flex flex-col shrink-0',
        // Slide animation on mobile
        'transform transition-transform duration-200 ease-in-out',
        // Mobile: show/hide based on isOpen
        isOpen ? 'translate-x-0' : '-translate-x-full',
        // Desktop (lg+): always visible, static in flow
        'lg:relative lg:translate-x-0 lg:z-auto',
      )}
    >
      {/* Logo row */}
      <div className="h-16 flex items-center justify-between px-5 border-b border-gray-200 shrink-0">
        <span className="text-lg font-bold text-blue-600">SubControl</span>
        {/* Close button — only visible on mobile */}
        <button
          onClick={onClose}
          className="lg:hidden p-1 text-gray-400 hover:text-gray-600 rounded transition"
          aria-label="Close menu"
        >
          <X size={20} />
        </button>
      </div>

      {/* Navigation links */}
      <ul className="flex-1 py-4 space-y-1 px-3 overflow-y-auto">
        {links.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === '/'}
              onClick={onClose}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
                )
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>

            {/* Quick-access bucket list, shown right under "Buckets" */}
            {to === '/buckets' && buckets.length > 0 && (
              <ul className="mt-1 ml-4 pl-3 space-y-0.5 border-l border-gray-100">
                {buckets.map((b) => (
                  <li key={b.id}>
                    <NavLink
                      to={`/buckets/${b.id}/subscriptions`}
                      onClick={onClose}
                      className={({ isActive }) =>
                        clsx(
                          'block px-2 py-1.5 rounded-md text-xs truncate transition-colors',
                          isActive
                            ? 'bg-blue-50 text-blue-700 font-medium'
                            : 'text-gray-500 hover:bg-gray-100 hover:text-gray-800',
                        )
                      }
                    >
                      {b.name}
                    </NavLink>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>

      {/* Version */}
      <div className="px-5 py-3 border-t border-gray-100 shrink-0">
        <p className="text-xs text-gray-400">v{version}</p>
      </div>
    </nav>
  )
}
