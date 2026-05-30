import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import CurrencyDisplay from '../components/CurrencyDisplay'

describe('CurrencyDisplay', () => {
  it('formats EUR correctly', () => {
    render(<CurrencyDisplay amount={9.99} currency="EUR" />)
    expect(screen.getByText(/9[.,]99/)).toBeInTheDocument()
  })

  it('formats USD correctly', () => {
    render(<CurrencyDisplay amount={19.5} currency="USD" />)
    expect(screen.getByText(/19[.,]50/)).toBeInTheDocument()
  })

  it('defaults to EUR when currency is omitted', () => {
    render(<CurrencyDisplay amount={5.0} />)
    expect(screen.getByText(/5[.,]00/)).toBeInTheDocument()
  })
})
