import { expect, test } from '@playwright/test';
import {
  ensureAuthStateExists,
  expectExecutedSlashCommand,
  expectInteractionLog,
  expectNoDiscordInteractionFailure,
  getLogCursor,
  latestChannelMessage,
  openDiscordTestChannel,
  readE2EEnv,
  runSlashCommand
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('/todo list directory', () => {
  test('shows the default server list directory with no input arguments', async ({ page }) => {
    const env = readE2EEnv();
    const logCursor = getLogCursor(env);

    await runSlashCommand(page, '/todo list directory');
    await expectNoDiscordInteractionFailure(page);

    const directoryMessage = latestChannelMessage(page, env.channelId);
    await expect(directoryMessage).toBeVisible({ timeout: 20_000 });
    await expectExecutedSlashCommand(directoryMessage, /todo\s+list\s+directory/i);
    await expect(directoryMessage).toContainText(/Todo List Directory/i);
    await expect(directoryMessage).toContainText(/Page\s+1\/\d+/);
    await expect(directoryMessage).toContainText(/Lists:\s*\d+/i);
    await expect(directoryMessage).toContainText(/Items:\s*\d+/i);
    await expect(directoryMessage).toContainText(/Sort:\s*ascending/i);
    await expect(directoryMessage).toContainText(/\[Server\]/i);
    await expect(directoryMessage.getByRole('button', { name: '1', exact: true })).toBeVisible({
      timeout: 10_000
    });
    await expectInteractionLog('todo list directory', logCursor);
  });
});
