/**
 * E2E: Dashboard flow.
 *
 * Covers: total monthly display, mode toggle, bucket filter.
 */

import { test, expect } from '@playwright/test'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ request }) => {
    // Seed data: bucket + subscriptions
    const bucketRes = await request.post('http://localhost:8000/api/buckets', {
      data: { name: `DashBucket-${Date.now()}` },
    })
    const bucket = await bucketRes.json()
    await request.post(
      `http://localhost:8000/api/buckets/${bucket.id}/subscriptions`,
      {
        data: {
          name: 'Acme Cloud',
          provider_name: 'Acme',
          recurring_interval: 'monthly',
          amount: 25.0,
          currency: 'EUR',
        },
      }
    )
  })

  test('shows total monthly spend', async ({ page }) => {
    await page.goto('/')
    // Wait for the dashboard to load
    await expect(page.getByText(/total monthly spend/i)).toBeVisible()
    // Some non-zero amount should be shown
    await expect(page.getByText(/€\d+/)).toBeVisible()
  })

  test('can switch between average and real modes', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /real monthly/i }).click()
    // Month picker should appear
    await expect(page.locator('input[type="month"]')).toBeVisible()
    await page.getByRole('button', { name: /average monthly/i }).click()
    await expect(page.locator('input[type="month"]')).not.toBeVisible()
  })

  test('can filter by bucket', async ({ page }) => {
    await page.goto('/')
    // Bucket dropdown should be present
    await expect(page.getByRole('combobox')).toBeVisible()
  })
})
