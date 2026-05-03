import path from 'node:path';
import dotenv from 'dotenv';
import { defineConfig, devices } from '@playwright/test';

dotenv.config({ path: path.resolve(__dirname, '.env'), quiet: true });

const authFile = path.resolve(__dirname, '.auth', 'discord-user.json');

export default defineConfig({
  testDir: './specs',
  timeout: 60_000,
  expect: {
    timeout: 10_000
  },
  fullyParallel: false,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { open: 'never' }]
  ],
  use: {
    baseURL: 'https://discord.com',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure'
  },
  projects: [
    {
      name: 'auth',
      testDir: './setup',
      testMatch: /auth\.setup\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: undefined
      }
    },
    {
      name: 'discord-chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: authFile
      }
    }
  ]
});
