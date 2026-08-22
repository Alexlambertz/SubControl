/**
 * E2E: Bucket management flows.
 *
 * Covers: create bucket, rename bucket, delete bucket.
 *
 * Each test creates uniquely-named buckets (timestamp suffix) and cleans
 * up after itself so tests remain independent of run order.
 */

import { test, expect } from '@playwright/test'

const API = 'http://127.0.0.1:8000/api'

test.describe('Bucket management', () => {
  // Track buckets created per test for cleanup
  const createdIds: string[] = []

  test.afterEach(async ({ request }) => {
    for (const id of createdIds.splice(0)) {
      await request.delete(`${API}/buckets/${id}`).catch(() => {})
    }
  })

  test.beforeEach(async ({ page }) => {
    await page.goto('/buckets')
    // Wait for the create form to confirm the page has loaded
    await expect(page.getByPlaceholder(/bucket name/i)).toBeVisible()
  })

  test('creates a new bucket', async ({ page, request }) => {
    const name = `E2E-Create-${Date.now()}`

    await page.getByPlaceholder(/bucket name/i).fill(name)
    await page.getByRole('button', { name: /^create$/i }).click()
    // Scoped to main: the sidebar's bucket quick-nav list also renders the name
    await expect(page.getByRole('main').getByText(name)).toBeVisible()

    // Register for cleanup
    const buckets = await request.get(`${API}/buckets`)
    const list = await buckets.json() as Array<{ id: string; name: string }>
    const created = list.find((b) => b.name === name)
    if (created) createdIds.push(created.id)
  })

  test('renames a bucket', async ({ page, request }) => {
    const oldName = `E2E-Rename-Old-${Date.now()}`
    const newName = `E2E-Rename-New-${Date.now()}`

    // Create via API for speed
    const res = await request.post(`${API}/buckets`, { data: { name: oldName } })
    const bucket = await res.json() as { id: string }
    createdIds.push(bucket.id)

    await page.reload()
    await expect(page.getByRole('main').getByText(oldName)).toBeVisible()

    // Click the Rename button for this bucket row
    await page.getByTitle(/rename/i).first().click()
    const editInput = page.getByRole('textbox').last()
    await editInput.clear()
    await editInput.fill(newName)
    await page.getByRole('button', { name: /^save$/i }).click()

    await expect(page.getByRole('main').getByText(newName)).toBeVisible()
    await expect(page.getByRole('main').getByText(oldName)).not.toBeVisible()
  })

  test('deletes a bucket', async ({ page, request }) => {
    const name = `E2E-Delete-${Date.now()}`

    const res = await request.post(`${API}/buckets`, { data: { name } })
    const bucket = await res.json() as { id: string }
    // Don't push to createdIds — the test deletes it

    await page.reload()
    await expect(page.getByRole('main').getByText(name)).toBeVisible()

    // Click Delete button for that specific row.
    // Use a dual-filter: div that contains the bucket name text AND has a Delete button.
    const row = page.locator('div').filter({ hasText: name }).filter({
      has: page.locator('[title="Delete"]'),
    }).last()
    await row.getByTitle(/delete/i).click()
    await page.getByRole('button', { name: /delete/i }).last().click()

    // exact: true avoids matching the dialog message "Delete "name" and all its subscriptions?"
    await expect(page.getByRole('main').getByText(name, { exact: true })).not.toBeVisible()

    // Verify it no longer exists via API
    const list = await (await request.get(`${API}/buckets`)).json() as Array<{ id: string }>
    expect(list.find((b: { id: string }) => b.id === bucket.id)).toBeUndefined()
  })

  test('shows empty state text when the bucket list is empty', async ({ page, request }) => {
    // Delete every existing bucket first so we get a clean state
    const listRes = await request.get(`${API}/buckets`)
    const existing = await listRes.json() as Array<{ id: string }>
    for (const b of existing) {
      await request.delete(`${API}/buckets/${b.id}`)
    }
    await page.reload()

    await expect(page.getByText(/no buckets yet/i)).toBeVisible()
  })
})
