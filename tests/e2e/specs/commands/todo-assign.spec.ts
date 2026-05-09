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

test.describe('/todo assign', () => {
  test('assigns an inserted todo selected from the required todo autocomplete', async ({ page }) => {
    const env = readE2EEnv();
    const addLogCursor = getLogCursor(env);
    const title = runMarker('e2e todo assign');

    await runSlashCommand(page, `/todo add ${title}`);
    await expectNoDiscordInteractionFailure(page);

    const addResponseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expectExecutedSlashCommand(addResponseMessage, /todo\s+add/i);
    await expect(addResponseMessage).toContainText(/Status\s*To Do/);
    await expect(addResponseMessage).toContainText(/Assignee\s*None/);
    await expectInteractionLog('todo add', addLogCursor);

    const assignLogCursor = getLogCursor(env);

    await runSlashCommandWithAutocompleteSelections(page, '/todo assign', [
      { query: title },
      { query: 'Me', selectionText: /^Me$/i }
    ]);
    await expectNoDiscordInteractionFailure(page);

    const assignResponseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expectExecutedSlashCommand(assignResponseMessage, /todo\s+assign/i);
    await expect(assignResponseMessage).toContainText(/Status\s*To Do/);
    await expect(assignResponseMessage).toContainText(/Assignee/i);
    await expect(assignResponseMessage).not.toContainText(/Assignee\s*None/);
    await expectInteractionLog('todo assign', assignLogCursor);
  });
});
