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
  runSlashCommand,
  runSlashCommandWithAutocompleteSelections
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('/todo status', () => {
  test('updates an inserted todo selected from the required todo autocomplete', async ({ page }) => {
    const env = readE2EEnv();
    const addLogCursor = getLogCursor(env);
    const title = runMarker('e2e todo status');

    await runSlashCommand(page, `/todo add ${title}`);
    await expectNoDiscordInteractionFailure(page);

    const addResponseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expectExecutedSlashCommand(addResponseMessage, /todo\s+add/i);
    await expect(addResponseMessage).toContainText(/Status\s*To Do/);
    await expectInteractionLog('todo add', addLogCursor);

    const statusLogCursor = getLogCursor(env);

    await runSlashCommandWithAutocompleteSelections(page, '/todo status', [
      { query: title },
      { query: 'In Progress', selectionText: /In Progress/i }
    ]);
    await expectNoDiscordInteractionFailure(page);

    const statusResponseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expectExecutedSlashCommand(statusResponseMessage, /todo\s+status/i);
    await expect(statusResponseMessage).toContainText(/Status\s*In Progress/);
    await expect(statusResponseMessage).toContainText(/Due\s*Not set/);
    await expect(statusResponseMessage).toContainText(/Assignee\s*None/);
    await expectInteractionLog('todo status', statusLogCursor);
  });
});
