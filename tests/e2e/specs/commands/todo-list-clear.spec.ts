import { expect, test, type Page } from '@playwright/test';
import {
  ensureAuthStateExists,
  expectDiscordModal,
  expectExecutedSlashCommand,
  expectInteractionLog,
  expectLatestChannelMessageContaining,
  expectNoDiscordInteractionFailure,
  getLogCursor,
  latestChannelMessage,
  openDiscordTestChannel,
  readE2EEnv,
  runMarker,
  runSlashCommand,
  runSlashCommandExpectingModal
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });
test.setTimeout(120_000);

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('/todo list clear', () => {
  test('clears the current list after confirmation with no input arguments', async ({ page }) => {
    const env = readE2EEnv();
    const setupPrefix = runMarker('e2e todo list clear');

    await clearCurrentTodoList(page);

    for (let index = 1; index <= 2; index += 1) {
      await runSlashCommand(page, `/todo add ${setupPrefix} ${index}`);
      await expectNoDiscordInteractionFailure(page);
      await expectLatestChannelMessageContaining(
        page,
        env.channelId,
        `${setupPrefix} ${index}`
      );
    }

    const clearLogCursor = getLogCursor(env);

    await runSlashCommandExpectingModal(page, '/todo list clear');
    await expectDiscordModal(page, /Clear Todo List/i);

    const dialog = page.getByRole('dialog').filter({ hasText: /Clear Todo List/i }).last();
    await expect(dialog).toContainText(/Current items:\s*2/i);
    await dialog.getByRole('button', { name: /submit/i }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
    await expectNoDiscordInteractionFailure(page);

    const clearMessage = latestChannelMessage(page, env.channelId);
    await expect(clearMessage).toBeVisible({ timeout: 20_000 });
    await expectExecutedSlashCommand(clearMessage, /todo\s+list\s+clear/i);
    await expect(clearMessage).toContainText(/Todo List Cleared/i);
    await expect(clearMessage).toContainText(/Removed items:\s*2/i);
    await expectInteractionLog('todo list clear', clearLogCursor);

    await runSlashCommand(page, '/todo list show');
    await expectNoDiscordInteractionFailure(page);

    const listMessage = latestChannelMessage(page, env.channelId);
    await expectExecutedSlashCommand(listMessage, /todo\s+list\s+show/i);
    await expect(listMessage).toContainText(/No items in this list\./i);
  });
});

async function clearCurrentTodoList(page: Page): Promise<void> {
  await runSlashCommandExpectingModal(page, '/todo list clear');
  await expectDiscordModal(page, /Clear Todo List/i);

  const dialog = page.getByRole('dialog').filter({ hasText: /Clear Todo List/i }).last();
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}
