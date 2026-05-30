/**
 * Displays a provider's logo image.
 * Falls back to a generic icon when the URL is missing or fails to load.
 */

import { useState } from 'react'
import { Building2 } from 'lucide-react'

interface Props {
  name: string | null
  imageUrl: string | null
  size?: number
}

export default function ProviderLogo({ name, imageUrl, size = 32 }: Props) {
  const [error, setError] = useState(false)

  if (!imageUrl || error) {
    return (
      <span
        className="inline-flex items-center justify-center rounded-lg bg-gray-100 text-gray-400"
        style={{ width: size, height: size }}
        title={name ?? ''}
      >
        <Building2 size={size * 0.6} />
      </span>
    )
  }

  return (
    <img
      src={imageUrl}
      alt={name ?? 'Provider logo'}
      width={size}
      height={size}
      className="rounded-lg object-contain bg-gray-50"
      onError={() => setError(true)}
    />
  )
}
