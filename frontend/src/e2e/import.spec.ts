/**
 * E2E: CSV import flow.
 *
 * Covers: upload valid CSV, view results, import with errors.
 */

import { test, expect } from '@playwright/test'
import path from 'path'
import fs from 'fs'
import os from 'os'

test.describe('CSV Import', () => {
  let bucketId: string

  test.beforeEach(async ({ request, page }) => {
    const res = await request.post('http://localhost:8000/api/buckets', {
      data: { name: `ImportBucket-${Date.now()}` },
    })
    const bucket = await res.json()
    bucketId = bucket.id
    await page.goto(`/buckets/${bucketId}/subscriptions`)
  })

  test('imports subscriptions from a valid CSV', async ({ page }) => {
    // Write a temp CSV file
    const csvContent = `name,provider,recurring_interval,amount,currency
Adobe CC,Adobe,monthly,54.99,EUR
GitHub Pro,GitHub,monthly,4.00,USD`

    const tmpFile = path.join(os.tmpdir(), `subcontrol_test_${Date.now()}.csv`)
    fs.writeFileSync(tmpFile, csvContent)

    try {
      // Navigate to CSV import page
      await page.getByRole('button', { name: /import/i }).click()
      await expect(page.getByText(/csv/i)).toBeVisible()

      await page.setInputFiles('input[type="file"]', tmpFile)
      await page.getByRole('button', { name: /upload|import/i }).click()

      // Success message
      await expect(page.getByText(/imported/i)).toBeVisible()
      await expect(page.getByText('Adobe CC')).toBeVisible()
    } finally {
      fs.unlinkSync(tmpFile)
    }
  })

  test('shows per-row errors for invalid CSV rows', async ({ page }) => {
    const csvContent = `name,provider,recurring_interval,amount,currency
Valid Sub,Netflix,monthly,9.99,EUR
,BadProvider,monthly,5.00,EUR`

    const tmpFile = path.join(os.tmpdir(), `subcontrol_err_${Date.now()}.csv`)
    fs.writeFileSync(tmpFile, csvContent)

    try {
      await page.getByRole('button', { name: /import/i }).click()
      await page.setInputFiles('input[type="file"]', tmpFile)
      await page.getByRole('button', { name: /upload|import/i }).click()

      // Should show partial success and the error
      await expect(page.getByText(/imported/i)).toBeVisible()
      await expect(page.getByText(/error|failed/i)).toBeVisible()
    } finally {
      fs.unlinkSync(tmpFile)
    }
  })
})
