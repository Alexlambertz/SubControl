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
    // Clear chat history stored in sessionStorage so we always see the empty state.
    // In DEV_MODE the dummy user id is 00000000000000000000000000000001.
    await page.addInitScript(() => {
      const DEV_USER_ID = '00000000000000000000000000000001'
      window.sessionStorage.removeItem(`subcontrol_chat_messages_${DEV_USER_ID}`)
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

    // Scoped to the thread: the sidebar's recent-conversations list can show
    // the same text as its (auto-generated) conversation title.
    await expect(
      page.getByTestId('chat-thread').getByText('How much am I spending?')
    ).toBeVisible()
  })

  test('Enter key sends the message', async ({ page }) => {
    const textarea = page.locator('textarea')
    await textarea.fill('Test via Enter')
    await textarea.press('Enter')

    await expect(
      page.getByTestId('chat-thread').getByText('Test via Enter')
    ).toBeVisible()
  })

  test('shows an AI response (or not-configured message) after sending', async ({ page }) => {
    const textarea = page.locator('textarea')
    await textarea.fill('Hello')
    await page.getByRole('button', { name: /send/i }).click()

    // Wait for the assistant bubble to appear and finish streaming.
    // Assistant bubbles have rounded-tl-sm (user bubbles have rounded-tr-sm),
    // so this selector never matches the outgoing "Hello" message.
    const assistantBubble = page.locator('.rounded-tl-sm')
    await expect(assistantBubble).toBeVisible({ timeout: 20000 })
    // Ensure the loading placeholder '…' has been replaced by real content
    await expect(assistantBubble).not.toHaveText('…', { timeout: 20000 })
  })
})
