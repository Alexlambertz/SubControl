/**
 * E2E: Subscription management flows.
 *
 * Covers: empty state, add subscription via UI, edit, delete.
 *
 * Each test gets a fresh bucket (created via API, cleaned up after).
 */

import { test, expect } from '@playwright/test'

const API = 'http://127.0.0.1:8000/api'

test.describe('Subscription management', () => {
  let bucketId: string

  test.beforeEach(async ({ request, page }) => {
    const res = await request.post(`${API}/buckets`, {
      data: { name: `SubBucket-${Date.now()}` },
    })
    const bucket = await res.json() as { id: string }
    bucketId = bucket.id
    await page.goto(`/buckets/${bucketId}/subscriptions`)
    // Wait for the page to finish loading
    await expect(
      page.getByRole('button', { name: /add subscription/i })
    ).toBeVisible({ timeout: 10000 })
  })

  test.afterEach(async ({ request }) => {
    await request.delete(`${API}/buckets/${bucketId}`).catch(() => {})
  })

  test('shows empty state when no subscriptions exist', async ({ page }) => {
    await expect(page.getByText(/no subscriptions/i)).toBeVisible()
  })

  test('adds a new subscription via the form', async ({ page }) => {
    await page.getByRole('button', { name: /add subscription/i }).click()

    // Fill in the required fields
    await page.getByPlaceholder(/netflix premium/i).fill('My Test Sub')
    await page.getByPlaceholder(/amount|9\.99/i).fill('14.99')
    // Submit the form
    await page.getByRole('button', { name: /^add$/i }).click()

    await expect(page.getByText('My Test Sub')).toBeVisible()
  })

  test('edits a subscription', async ({ page, request }) => {
    // Seed via API
    await request.post(`${API}/buckets/${bucketId}/subscriptions`, {
      data: {
        name: 'EditMe',
        provider_name: 'TestCo',
        recurring_interval: 'monthly',
        amount: 9.99,
        currency: 'EUR',
      },
    })
    await page.reload()
    await expect(page.getByText('EditMe')).toBeVisible()

    // Open edit form via the Edit button on the row
    await page.getByTitle(/edit/i).first().click()
    const amountInput = page.getByPlaceholder(/amount|9\.99/i)
    await amountInput.clear()
    await amountInput.fill('19.99')
    await page.getByRole('button', { name: /save changes/i }).click()

    await expect(page.getByText('19.99')).toBeVisible()
  })

  test('deletes a subscription', async ({ page, request }) => {
    await request.post(`${API}/buckets/${bucketId}/subscriptions`, {
      data: {
        name: 'DeleteMe',
        provider_name: 'TestCo',
        recurring_interval: 'monthly',
        amount: 5.0,
        currency: 'EUR',
      },
    })
    await page.reload()
    await expect(page.getByText('DeleteMe', { exact: true })).toBeVisible()

    await page.getByTitle(/delete/i).first().click()
    // Confirm in the dialog
    await page.getByRole('button', { name: /delete/i }).last().click()

    // exact: true avoids matching the dialog message "Delete "DeleteMe"? …"
    await expect(page.getByText('DeleteMe', { exact: true })).not.toBeVisible()
  })
})
