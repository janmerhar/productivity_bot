import { expect, test, type Locator } from '@playwright/test';
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
  runSlashCommand,
  runSlashCommandWithOptions
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('/todo add', () => {
  test('creates a todo with only the required argument', async ({ page }) => {
    const env = readE2EEnv();
    const logCursor = getLogCursor(env);
    const title = runMarker('e2e todo required');

    await runSlashCommand(page, `/todo add ${title}`);
    await expectNoDiscordInteractionFailure(page);

    const responseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expectTodoAddResponse(responseMessage);
    await expectInteractionLog('todo add', logCursor);
  });

  test('creates a todo with a description', async ({ page }) => {
    const env = readE2EEnv();
    const logCursor = getLogCursor(env);
    const title = runMarker('e2e todo described');
    const description = runMarker('e2e todo description');

    await runSlashCommandWithOptions(page, `/todo add ${title}`, [
      { name: 'description', value: description }
    ]);
    await expectNoDiscordInteractionFailure(page);

    const responseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expectTodoAddResponse(responseMessage);
    await expect(responseMessage).toContainText(description);
    await expectInteractionLog('todo add', logCursor);
  });
});

async function expectTodoAddResponse(responseMessage: Locator): Promise<void> {
  await expectExecutedSlashCommand(responseMessage, /todo\s+add/i);
  await expect(responseMessage).toContainText(/Status\s*To Do/);
  await expect(responseMessage).toContainText(/Due\s*Not set/);
  await expect(responseMessage).toContainText(/Assignee\s*None/);
}
