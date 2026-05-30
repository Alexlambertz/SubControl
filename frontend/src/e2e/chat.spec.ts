/**
 * E2E: AI Chat flow.
 *
 * Covers: page loads, user can type and send a message, response appears.
 * Note: actual AI call is not made — we verify the UI flows correctly and
 * the error state is shown when AI is not configured.
 */

import { test, expect } from '@playwright/test'

test.describe('AI Chat', () => {
  test('chat page loads with empty state', async ({ page }) => {
    await page.goto('/chat')
    await expect(page.getByText(/ask me about your subscriptions/i)).toBeVisible()
  })

  test('user message appears after sending', async ({ page }) => {
    await page.goto('/chat')

    const textarea = page.locator('textarea')
    await textarea.fill('How much am I spending?')
    await page.getByRole('button', { name: /send/i }).click()

    // User message should appear
    await expect(page.getByText('How much am I spending?')).toBeVisible()
  })

  test('shows error/config message when AI is not set up', async ({ page }) => {
    await page.goto('/chat')

    const textarea = page.locator('textarea')
    await textarea.fill('Hello')
    await page.getByRole('button', { name: /send/i }).click()

    // Wait for assistant response (even if it's the "not configured" message)
    await expect(
      page.getByText(/not configured|ai_api_url|failed/i)
    ).toBeVisible({ timeout: 10000 })
  })

  test('can abort a message with Enter key', async ({ page }) => {
    await page.goto('/chat')

    const textarea = page.locator('textarea')
    await textarea.fill('Test message')
    await textarea.press('Enter')

    await expect(page.getByText('Test message')).toBeVisible()
  })
})
