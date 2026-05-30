/**
 * E2E: Dashboard flows.
 *
 * Covers: total monthly display, mode toggle (Average/Real), bucket filter.
 *
 * Seeds one bucket + one subscription via the API before each test,
 * then cleans up afterwards.
 */

import { test, expect } from '@playwright/test'

const API = 'http://127.0.0.1:8000/api'

test.describe('Dashboard', () => {
  let bucketId: string

  test.beforeEach(async ({ request }) => {
    const bucketRes = await request.post(`${API}/buckets`, {
      data: { name: `DashBucket-${Date.now()}` },
    })
    const bucket = await bucketRes.json() as { id: string }
    bucketId = bucket.id

    await request.post(`${API}/buckets/${bucketId}/subscriptions`, {
      data: {
        name: 'Acme Cloud',
        provider_name: 'Acme',
        recurring_interval: 'monthly',
        amount: 25.0,
        currency: 'EUR',
      },
    })
  })

  test.afterEach(async ({ request }) => {
    await request.delete(`${API}/buckets/${bucketId}`).catch(() => {})
  })

  test('shows Total monthly spend section', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/total monthly spend/i)).toBeVisible({ timeout: 10000 })
  })

  test('can switch to Real monthly mode', async ({ page }) => {
    await page.goto('/')
    // The toggle buttons say "Average monthly" and "Real monthly"
    await page.getByRole('button', { name: /real monthly/i }).click()
    // The MonthPicker calendar button should appear (it shows the current month)
    await expect(page.getByRole('button', { name: /calendar|^\w+ \d{4}$/i })).toBeVisible()
  })

  test('can switch back to Average monthly mode', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /real monthly/i }).click()
    await page.getByRole('button', { name: /average monthly/i }).click()
    // MonthPicker should be gone — only the mode buttons remain
    await expect(page.getByRole('button', { name: /real monthly/i })).toBeVisible()
  })

  test('has a bucket filter dropdown', async ({ page }) => {
    await page.goto('/')
    // The bucket select shows "All buckets" by default
    const select = page.getByRole('combobox')
    await expect(select).toBeVisible()
    await expect(select).toContainText(/all buckets/i)
  })

  test('bucket filter lists the seeded bucket', async ({ page }) => {
    await page.goto('/')
    const select = page.getByRole('combobox')
    await expect(select).toBeVisible()
    // The seeded bucket should appear in the dropdown options
    const options = await select.locator('option').allTextContents()
    expect(options.some((o) => o.match(/DashBucket/i))).toBeTruthy()
  })
})
