import fs from 'node:fs';
import path from 'node:path';
import { expect, test as setup } from '@playwright/test';

const authFile = path.resolve(__dirname, '..', '.auth', 'discord-user.json');

setup('save Discord browser session', async ({ page }) => {
  fs.mkdirSync(path.dirname(authFile), { recursive: true });

  await page.goto('https://discord.com/channels/@me');

  console.log('');
  console.log('Log in to Discord in the opened browser window.');
  console.log('Use a dedicated test account, then wait until Discord shows the app UI.');
  console.log(`Saving browser auth state to ${authFile}`);
  console.log('');

  await expect(page).toHaveURL(/https:\/\/discord\.com\/channels\//, {
    timeout: 180_000
  });

  await expect(
    page
      .locator('[data-list-id="guildsnav"], [aria-label="Servers"], [aria-label="Servers sidebar"]')
      .first()
  ).toBeVisible({ timeout: 180_000 });

  await page.context().storageState({ path: authFile });
});
