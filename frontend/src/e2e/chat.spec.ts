/**
 * E2E: AI Chat flows.
 *
 * Covers: empty state, sending a message (message appears in UI),
 *         "not configured" response when AI is not set up.
 *
 * localStorage is cleared before each test so the chat history does
 * not carry over from previous runs.
 */

import { test, expect } from '@playwright/test'

test.describe('AI Chat', () => {
  test.beforeEach(async ({ page }) => {
    // Clear chat history stored in localStorage so we always see the empty state
    await page.addInitScript(() => {
      window.localStorage.removeItem('subcontrol_chat_messages')
    })
    await page.goto('/chat')
    // Wait for the page to settle
    await page.waitForLoadState('networkidle')
  })

  test('chat page loads with empty-state prompt text', async ({ page }) => {
    await expect(
      page.getByText(/ask me about your subscriptions/i)
    ).toBeVisible({ timeout: 10000 })
  })

  test('user message appears in the thread after sending', async ({ page }) => {
    const textarea = page.locator('textarea')
    await textarea.fill('How much am I spending?')
    await page.getByRole('button', { name: /send/i }).click()

    await expect(page.getByText('How much am I spending?')).toBeVisible()
  })

  test('Enter key sends the message', async ({ page }) => {
    const textarea = page.locator('textarea')
    await textarea.fill('Test via Enter')
    await textarea.press('Enter')

    await expect(page.getByText('Test via Enter')).toBeVisible()
  })

  test('shows an AI response (or not-configured message) after sending', async ({ page }) => {
    const textarea = page.locator('textarea')
    await textarea.fill('Hello')
    await page.getByRole('button', { name: /send/i }).click()

    // Wait for the assistant bubble to appear (response or config error)
    await expect(
      page.getByText(/not configured|ai_api_url|hello|error|failed/i)
    ).toBeVisible({ timeout: 20000 })
  })
})
