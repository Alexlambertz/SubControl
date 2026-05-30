/**
 * Formats a monetary amount with its currency symbol.
 */



interface Props {
  amount: number
  currency?: string
  className?: string
}

export default function CurrencyDisplay({
  amount,
  currency = 'EUR',
  className,
}: Props) {
  const formatted = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)

  return <span className={className}>{formatted}</span>
}
