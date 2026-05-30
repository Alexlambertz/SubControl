/**
 * User list page — admin only.
 *
 * Shows all users with:
 *  - Admin badge + toggle to grant/revoke admin (cannot revoke own admin)
 *  - Bucket-access modal: shows all buckets with checkboxes per user
 *  - Delete button with confirmation
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2, ShieldCheck, FolderKey, X } from 'lucide-react'
import { usersApi } from '../../api/users'
import { bucketsApi } from '../../api/buckets'
import { useAuth } from '../../auth/AuthContext'
import ConfirmDialog from '../../components/ConfirmDialog'
import type { Bucket, User } from '../../types'

// ---------------------------------------------------------------------------
// Bucket-access modal
// ---------------------------------------------------------------------------

function BucketAccessModal({
  user,
  onClose,
}: {
  user: User
  onClose: () => void
}) {
  const qc = useQueryClient()

  const { data: allBuckets = [] } = useQuery<Bucket[]>({
    queryKey: ['buckets'],
    queryFn: bucketsApi.list,
  })

  const { data: assignedIds = [], isLoading } = useQuery<string[]>({
    queryKey: ['user-buckets', user.id],
    queryFn: () => usersApi.getBuckets(user.id),
  })

  const assignMut = useMutation({
    mutationFn: (bucketId: string) => bucketsApi.assignUser(bucketId, user.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['user-buckets', user.id] }),
  })

  const removeMut = useMutation({
    mutationFn: (bucketId: string) => bucketsApi.removeUser(bucketId, user.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['user-buckets', user.id] }),
  })

  const toggle = (bucketId: string, currentlyAssigned: boolean) => {
    if (currentlyAssigned) {
      removeMut.mutate(bucketId)
    } else {
      assignMut.mutate(bucketId)
    }
  }

  const busy = assignMut.isPending || removeMut.isPending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <p className="font-semibold text-gray-800">Bucket access</p>
            <p className="text-xs text-gray-400 mt-0.5">{user.username}</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition"
          >
            <X size={16} />
          </button>
        </div>

        {/* Bucket list */}
        <div className="px-5 py-3 max-h-72 overflow-y-auto">
          {isLoading ? (
            <p className="text-sm text-gray-400 py-4 text-center">Loading…</p>
          ) : allBuckets.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">No buckets exist yet.</p>
          ) : (
            <ul className="space-y-1">
              {allBuckets.map((bucket) => {
                const assigned = assignedIds.includes(bucket.id)
                return (
                  <li key={bucket.id}>
                    <label className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-gray-50 cursor-pointer transition select-none">
                      <input
                        type="checkbox"
                        checked={assigned}
                        disabled={busy}
                        onChange={() => toggle(bucket.id, assigned)}
                        className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer disabled:opacity-50"
                      />
                      <span className="text-sm text-gray-700">{bucket.name}</span>
                    </label>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="px-5 py-3 border-t border-gray-100">
          <button
            onClick={onClose}
            className="w-full py-2 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl transition"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function UserList() {
  const qc = useQueryClient()
  const { user: me } = useAuth()
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null)
  const [bucketTarget, setBucketTarget] = useState<User | null>(null)

  const { data: users = [], isLoading } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: usersApi.list,
  })

  const adminMut = useMutation({
    mutationFn: ({ id, isAdmin }: { id: string; isAdmin: boolean }) =>
      usersApi.setAdmin(id, isAdmin),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
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
            <p className="py-8 text-center text-gray-400 text-sm">No users found.</p>
          ) : (
            users.map((user) => {
              const isMe = user.id === me?.id
              return (
                <div
                  key={user.id}
                  className="flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition"
                >
                  {/* Identity */}
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-800 truncate">
                        {user.username}
                      </span>
                      {user.is_admin && (
                        <span className="inline-flex items-center gap-1 text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full shrink-0">
                          <ShieldCheck size={11} />
                          admin
                        </span>
                      )}
                      {isMe && (
                        <span className="text-xs text-gray-400 shrink-0">(you)</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Last login:{' '}
                      {user.last_login
                        ? new Date(user.last_login).toLocaleString()
                        : 'Never'}
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 shrink-0 ml-4">
                    {/* Bucket access */}
                    <button
                      onClick={() => setBucketTarget(user)}
                      className="p-1.5 text-gray-400 hover:text-blue-600 rounded-lg hover:bg-blue-50 transition"
                      title="Manage bucket access"
                    >
                      <FolderKey size={15} />
                    </button>

                    {/* Admin toggle — disabled for self (prevent lockout) */}
                    <button
                      onClick={() =>
                        adminMut.mutate({ id: user.id, isAdmin: !user.is_admin })
                      }
                      disabled={isMe || adminMut.isPending}
                      className={[
                        'p-1.5 rounded-lg transition',
                        isMe
                          ? 'opacity-30 cursor-not-allowed text-gray-400'
                          : user.is_admin
                          ? 'text-blue-600 hover:text-gray-500 hover:bg-gray-100'
                          : 'text-gray-400 hover:text-blue-600 hover:bg-blue-50',
                      ].join(' ')}
                      title={
                        isMe
                          ? 'Cannot change your own admin status'
                          : user.is_admin
                          ? 'Revoke admin'
                          : 'Grant admin'
                      }
                    >
                      <ShieldCheck size={15} />
                    </button>

                    {/* Delete */}
                    <button
                      onClick={() => setDeleteTarget(user)}
                      disabled={isMe}
                      className={[
                        'p-1.5 rounded-lg transition',
                        isMe
                          ? 'opacity-30 cursor-not-allowed text-gray-400'
                          : 'text-gray-400 hover:text-red-600 hover:bg-red-50',
                      ].join(' ')}
                      title={isMe ? 'Cannot delete yourself' : 'Delete user'}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              )
            })
          )}
        </div>
      )}

      {/* Bucket access modal */}
      {bucketTarget && (
        <BucketAccessModal
          user={bucketTarget}
          onClose={() => setBucketTarget(null)}
        />
      )}

      {/* Delete confirmation */}
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
