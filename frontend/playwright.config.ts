import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E configuration.
 *
 * The tests expect:
 * - Backend: http://localhost:8000  (started automatically via webServer)
 * - Frontend: http://localhost:5173 (Vite dev server, started automatically)
 *
 * Both servers are auto-started when running `npm run test:e2e`.
 * Set DEV_MODE=true so no OIDC login is required.
 */
export default defineConfig({
  testDir: './src/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'DEV_MODE=true DATABASE_URL="sqlite+aiosqlite:///./e2e_test.db" backend/.venv/bin/uvicorn backend.main:app --port 8000',
      url: 'http://localhost:8000/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 30000,
      cwd: '../',
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 30000,
    },
  ],
})
