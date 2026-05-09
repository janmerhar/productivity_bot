import { expect, test } from '@playwright/test';
import {
  ensureAuthStateExists,
  expectExecutedSlashCommand,
  expectInteractionLog,
  expectLatestChannelMessageContaining,
  expectNoDiscordInteractionFailure,
  getLogCursor,
  openDiscordTestChannel,
  readE2EEnv,
  runMarker,
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

test.describe('/todo list create', () => {
  test('creates a custom todo list with only the required name argument', async ({ page }) => {
    const env = readE2EEnv();
    const logCursor = getLogCursor(env);
    const listName = runMarker('e2e todo list create');

    await runSlashCommand(page, `/todo list create ${listName}`);
    await expectNoDiscordInteractionFailure(page);

    const responseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      listName
    );
    await expectExecutedSlashCommand(responseMessage, /todo\s+list\s+create/i);
    await expect(responseMessage).toContainText(/Todo List Created/i);
    await expect(responseMessage).toContainText(/Items:\s*0/i);
    await expectInteractionLog('todo list create', logCursor);
  });
});
