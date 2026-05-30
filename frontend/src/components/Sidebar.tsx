/**
 * Application sidebar with navigation links.
 * Admin-only links (Users, Settings) are hidden for non-admin users.
 */

import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  FolderOpen,
  Users,
  MessageSquare,
  Settings,
  Upload,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../auth/AuthContext'

const allLinks = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, adminOnly: false },
  { to: '/buckets', label: 'Buckets', icon: FolderOpen, adminOnly: false },
  { to: '/import', label: 'Import', icon: Upload, adminOnly: false },
  { to: '/chat', label: 'AI Chat', icon: MessageSquare, adminOnly: false },
  { to: '/users', label: 'Users', icon: Users, adminOnly: true },
  { to: '/settings', label: 'Settings', icon: Settings, adminOnly: true },
]

export default function Sidebar() {
  const { user } = useAuth()
  const isAdmin = user?.is_admin ?? false
  const links = allLinks.filter((l) => !l.adminOnly || isAdmin)

  return (
    <nav className="w-56 bg-white border-r border-gray-200 flex flex-col shrink-0">
      {/* Logo */}
      <div className="h-16 flex items-center px-5 border-b border-gray-200">
        <span className="text-lg font-bold text-blue-600">SubControl</span>
      </div>

      {/* Navigation links */}
      <ul className="flex-1 py-4 space-y-1 px-3">
        {links.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                )
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
