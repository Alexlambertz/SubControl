/**
 * User list page — admin only.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2, ShieldCheck } from 'lucide-react'
import { usersApi } from '../../api/users'
import ConfirmDialog from '../../components/ConfirmDialog'
import type { User } from '../../types'

export default function UserList() {
  const qc = useQueryClient()
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null)

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: usersApi.list,
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => usersApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      setDeleteTarget(null)
    },
  })

  return (
    <div className="space-y-5">
      {isLoading ? (
        <div className="text-gray-400 text-center py-12">Loading…</div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
          {users.length === 0 ? (
            <p className="py-8 text-center text-gray-400 text-sm">
              No users found.
            </p>
          ) : (
            users.map((user) => (
              <div
                key={user.id}
                className="flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-800">
                      {user.username}
                    </span>
                    {user.is_admin && (
                      <span className="inline-flex items-center gap-1 text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">
                        <ShieldCheck size={11} />
                        admin
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Last login:{' '}
                    {user.last_login
                      ? new Date(user.last_login).toLocaleString()
                      : 'Never'}
                  </p>
                </div>
                <button
                  onClick={() => setDeleteTarget(user)}
                  className="p-1.5 text-gray-400 hover:text-red-600 rounded transition"
                  title="Delete user"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete user"
          message={`Remove user "${deleteTarget.username}"? This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => deleteMut.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}
