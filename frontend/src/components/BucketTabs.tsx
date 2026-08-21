/**
 * Tab bar switching between a bucket's Subscriptions and Insurances pages.
 */

import { NavLink } from 'react-router-dom'
import { CreditCard, Shield } from 'lucide-react'

interface Props {
  bucketId: string
}

const TABS = [
  { path: (id: string) => `/buckets/${id}/subscriptions`, label: 'Subscriptions', icon: CreditCard },
  { path: (id: string) => `/buckets/${id}/insurances`, label: 'Insurances', icon: Shield },
] as const

export default function BucketTabs({ bucketId }: Props) {
  return (
    <div className="flex rounded-lg overflow-hidden border border-gray-200 bg-white w-fit">
      {TABS.map(({ path, label, icon: Icon }) => (
        <NavLink
          key={label}
          to={path(bucketId)}
          className={({ isActive }) =>
            `flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition ${
              isActive ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
            }`
          }
        >
          <Icon size={14} />
          {label}
        </NavLink>
      ))}
    </div>
  )
}
