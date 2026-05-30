/**
 * E2E: Bucket management flows.
 *
 * Covers: create bucket, list buckets, rename bucket, delete bucket.
 */

import { test, expect } from '@playwright/test'

test.describe('Bucket management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/buckets')
    await expect(page).toHaveURL(/\/buckets/)
  })

  test('shows empty state when no buckets exist', async ({ page }) => {
    await expect(page.getByText(/no buckets/i)).toBeVisible()
  })

  test('creates a new bucket', async ({ page }) => {
    await page.getByRole('button', { name: /new bucket/i }).click()
    await page.getByPlaceholder(/bucket name/i).fill('Personal')
    await page.getByRole('button', { name: /create/i }).click()
    await expect(page.getByText('Personal')).toBeVisible()
  })

  test('renames a bucket', async ({ page }) => {
    // Create first
    await page.getByRole('button', { name: /new bucket/i }).click()
    await page.getByPlaceholder(/bucket name/i).fill('OldName')
    await page.getByRole('button', { name: /create/i }).click()
    await expect(page.getByText('OldName')).toBeVisible()

    // Rename
    await page.getByTitle(/rename/i).first().click()
    await page.getByRole('textbox').fill('NewName')
    await page.getByRole('button', { name: /save|rename/i }).click()
    await expect(page.getByText('NewName')).toBeVisible()
    await expect(page.getByText('OldName')).not.toBeVisible()
  })

  test('deletes a bucket', async ({ page }) => {
    // Create first
    await page.getByRole('button', { name: /new bucket/i }).click()
    await page.getByPlaceholder(/bucket name/i).fill('ToDelete')
    await page.getByRole('button', { name: /create/i }).click()
    await expect(page.getByText('ToDelete')).toBeVisible()

    // Delete
    await page.getByTitle(/delete/i).first().click()
    // Confirm dialog
    await page.getByRole('button', { name: /delete|confirm/i }).click()
    await expect(page.getByText('ToDelete')).not.toBeVisible()
  })
})
