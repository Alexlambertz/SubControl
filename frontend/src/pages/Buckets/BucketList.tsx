/**
 * Bucket list page — CRUD for buckets.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, Pencil, Trash2, FolderOpen } from 'lucide-react'
import { bucketsApi } from '../../api/buckets'
import ConfirmDialog from '../../components/ConfirmDialog'
import type { Bucket } from '../../types'

export default function BucketList() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [newName, setNewName] = useState('')
  const [editId, setEditId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Bucket | null>(null)
  const [error, setError] = useState('')

  const { data: buckets = [], isLoading } = useQuery({
    queryKey: ['buckets'],
    queryFn: bucketsApi.list,
  })

  const createMut = useMutation({
    mutationFn: (name: string) => bucketsApi.create(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['buckets'] })
      setNewName('')
      setError('')
    },
    onError: (e: Error) => setError(e.message),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      bucketsApi.update(id, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['buckets'] })
      setEditId(null)
    },
    onError: (e: Error) => setError(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => bucketsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['buckets'] })
      setDeleteTarget(null)
    },
  })

  return (
    <div className="space-y-6">
      {/* Create form */}
      <div className="bg-white rounded-2xl border border-gray-200 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">New bucket</h2>
        <form
          className="flex gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (newName.trim()) createMut.mutate(newName.trim())
          }}
        >
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Bucket name…"
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
          />
          <button
            type="submit"
            className="flex items-center gap-2 bg-blue-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-700 transition"
          >
            <Plus size={16} />
            Create
          </button>
        </form>
        {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
      </div>

      {/* List */}
      {isLoading ? (
        <div className="text-gray-400 text-center py-8">Loading…</div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
          {buckets.length === 0 ? (
            <p className="py-8 text-center text-gray-400 text-sm">
              No buckets yet. Create one above.
            </p>
          ) : (
            buckets.map((bucket) => (
              <div
                key={bucket.id}
                onClick={() => navigate(`/buckets/${bucket.id}/subscriptions`)}
                className="flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition cursor-pointer"
              >
                {editId === bucket.id ? (
                  <form
                    className="flex-1 flex gap-2"
                    onClick={(e) => e.stopPropagation()}
                    onSubmit={(e) => {
                      e.preventDefault()
                      updateMut.mutate({ id: bucket.id, name: editName })
                    }}
                  >
                    <input
                      autoFocus
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="flex-1 border border-gray-200 rounded-lg px-2 py-1 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                    <button
                      type="submit"
                      className="text-xs bg-blue-600 text-white px-3 py-1 rounded-lg"
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditId(null)}
                      className="text-xs text-gray-500 px-3 py-1 rounded-lg border border-gray-200"
                    >
                      Cancel
                    </button>
                  </form>
                ) : (
                  <>
                    <div
                      className="flex items-center gap-2 text-sm font-medium text-gray-800"
                    >
                      <FolderOpen size={16} className="text-gray-400" />
                      {bucket.name}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setEditId(bucket.id)
                          setEditName(bucket.name)
                        }}
                        className="p-1.5 text-gray-400 hover:text-blue-600 rounded transition"
                        title="Rename"
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteTarget(bucket)
                        }}
                        className="p-1.5 text-gray-400 hover:text-red-600 rounded transition"
                        title="Delete"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Confirm delete dialog */}
      {deleteTarget && (
        <ConfirmDialog
          title="Delete bucket"
          message={`Delete "${deleteTarget.name}" and all its subscriptions? This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => deleteMut.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}
