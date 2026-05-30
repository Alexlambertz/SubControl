/**
 * E2E: Subscription management flows.
 *
 * Covers: add subscription, view list, edit, delete.
 */

import { test, expect } from '@playwright/test'

test.describe('Subscription management', () => {
  let bucketId: string

  test.beforeEach(async ({ request, page }) => {
    // Create a bucket via API so we have a clean starting point
    const res = await request.post('http://localhost:8000/api/buckets', {
      data: { name: `TestBucket-${Date.now()}` },
    })
    const bucket = await res.json()
    bucketId = bucket.id
    await page.goto(`/buckets/${bucketId}/subscriptions`)
  })

  test('shows empty state when no subscriptions', async ({ page }) => {
    await expect(page.getByText(/no subscriptions/i)).toBeVisible()
  })

  test('adds a new subscription', async ({ page }) => {
    await page.getByRole('button', { name: /add subscription/i }).click()

    await page.getByLabel(/name/i).fill('Netflix Premium')
    await page.getByLabel(/provider/i).fill('Netflix')
    await page.getByLabel(/amount/i).fill('15.99')
    await page.getByRole('button', { name: /^add$/i }).click()

    await expect(page.getByText('Netflix Premium')).toBeVisible()
  })

  test('edits a subscription', async ({ page, request }) => {
    // Create via API
    await request.post(
      `http://localhost:8000/api/buckets/${bucketId}/subscriptions`,
      {
        data: {
          name: 'Spotify',
          provider_name: 'Spotify',
          recurring_interval: 'monthly',
          amount: 9.99,
          currency: 'EUR',
        },
      }
    )
    await page.reload()

    await page.getByText('Spotify').click()
    // Open edit form
    await page.getByRole('button', { name: /edit/i }).click()
    await page.getByLabel(/amount/i).fill('12.99')
    await page.getByRole('button', { name: /save changes/i }).click()

    await expect(page.getByText('12.99')).toBeVisible()
  })

  test('deletes a subscription', async ({ page, request }) => {
    await request.post(
      `http://localhost:8000/api/buckets/${bucketId}/subscriptions`,
      {
        data: {
          name: 'YouTube Premium',
          provider_name: 'Google',
          recurring_interval: 'monthly',
          amount: 11.99,
          currency: 'EUR',
        },
      }
    )
    await page.reload()
    await expect(page.getByText('YouTube Premium')).toBeVisible()

    await page.getByRole('button', { name: /delete/i }).first().click()
    await page.getByRole('button', { name: /delete|confirm/i }).click()
    await expect(page.getByText('YouTube Premium')).not.toBeVisible()
  })
})
