/**
 * E2E: CSV import flow.
 *
 * Covers: upload valid CSV → subscriptions imported,
 *         CSV with all-bad rows → error message stays visible.
 *
 * NOTES:
 * - CsvImport has no explicit "Upload" button: selecting the file via the
 *   hidden <input type="file"> immediately starts the upload.
 * - When imported > 0, onImported() is called which unmounts the panel
 *   before setResult renders, so we verify success by checking that the
 *   subscription names appear in the list after the panel closes.
 * - When imported === 0 (all rows fail), the panel stays open and shows
 *   the per-row error summary.
 */

import { test, expect } from '@playwright/test'
import path from 'path'
import fs from 'fs'
import os from 'os'

const API = 'http://127.0.0.1:8000/api'

test.describe('CSV Import', () => {
  let bucketId: string

  test.beforeEach(async ({ request, page }) => {
    const res = await request.post(`${API}/buckets`, {
      data: { name: `ImportBucket-${Date.now()}` },
    })
    const bucket = await res.json() as { id: string }
    bucketId = bucket.id

    await page.goto(`/buckets/${bucketId}/subscriptions`)
    await expect(
      page.getByRole('button', { name: /add subscription/i })
    ).toBeVisible({ timeout: 10000 })
  })

  test.afterEach(async ({ request }) => {
    await request.delete(`${API}/buckets/${bucketId}`).catch(() => {})
  })

  test('imports subscriptions from a valid CSV', async ({ page }) => {
    const csvContent = [
      'name,provider,recurring_interval,amount,currency',
      'Adobe CC,Adobe,monthly,54.99,EUR',
      'GitHub Pro,GitHub,monthly,4.00,USD',
    ].join('\n')

    const tmpFile = path.join(os.tmpdir(), `subcontrol_ok_${Date.now()}.csv`)
    fs.writeFileSync(tmpFile, csvContent)

    try {
      // Open the CSV import panel
      await page.getByRole('button', { name: /import csv/i }).click()
      // Selecting the file starts the upload immediately (no separate Upload button)
      await page.setInputFiles('input[type="file"]', tmpFile)

      // Panel closes via onImported(); wait for subscription names in the list
      await expect(page.getByText('Adobe CC')).toBeVisible({ timeout: 10000 })
      await expect(page.getByText('GitHub Pro')).toBeVisible()
    } finally {
      fs.unlinkSync(tmpFile)
    }
  })

  test('shows per-row errors for invalid CSV rows', async ({ page }) => {
    // All rows have no name → imported === 0 → panel stays open showing errors
    const csvContent = [
      'name,provider,recurring_interval,amount,currency',
      ',BadProvider1,monthly,5.00,EUR',
      ',BadProvider2,monthly,3.00,EUR',
    ].join('\n')

    const tmpFile = path.join(os.tmpdir(), `subcontrol_err_${Date.now()}.csv`)
    fs.writeFileSync(tmpFile, csvContent)

    try {
      await page.getByRole('button', { name: /import csv/i }).click()
      await page.setInputFiles('input[type="file"]', tmpFile)

      // Panel stays open — the "N rows failed" message should be visible
      await expect(page.getByText(/failed/i)).toBeVisible({ timeout: 10000 })
    } finally {
      fs.unlinkSync(tmpFile)
    }
  })
})
