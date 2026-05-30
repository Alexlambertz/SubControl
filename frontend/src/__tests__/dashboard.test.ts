/**
 * Unit tests for the monthly conversion utility — mirrors the backend logic.
 */

import { describe, it, expect } from 'vitest'

// Conversion factors (must stay in sync with backend/services/dashboard.py)
const FACTORS: Record<string, number> = {
  daily: 30.0,
  weekly: 365.0 / 12.0 / 7.0,
  monthly: 1.0,
  quarterly: 1.0 / 3.0,
  'half-year': 1.0 / 6.0,
  yearly: 1.0 / 12.0,
}

function toMonthlyAverage(amount: number, interval: string): number {
  return amount * (FACTORS[interval] ?? 1.0)
}

describe('toMonthlyAverage', () => {
  it('monthly is unchanged', () => {
    expect(toMonthlyAverage(10, 'monthly')).toBeCloseTo(10)
  })

  it('daily × 30', () => {
    expect(toMonthlyAverage(1, 'daily')).toBeCloseTo(30)
  })

  it('weekly × 4.33', () => {
    expect(toMonthlyAverage(10, 'weekly')).toBeCloseTo(43.33, 0)
  })

  it('quarterly ÷ 3', () => {
    expect(toMonthlyAverage(30, 'quarterly')).toBeCloseTo(10)
  })

  it('half-year ÷ 6', () => {
    expect(toMonthlyAverage(60, 'half-year')).toBeCloseTo(10)
  })

  it('yearly ÷ 12', () => {
    expect(toMonthlyAverage(120, 'yearly')).toBeCloseTo(10)
  })
})
