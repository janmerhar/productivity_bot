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
  runSlashCommandWithAutocompleteSelection
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('/todo delete', () => {
  test('deletes an inserted todo selected from the required todo autocomplete', async ({ page }) => {
    const env = readE2EEnv();
    const addLogCursor = getLogCursor(env);
    const title = runMarker('e2e todo delete');

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

    const deleteLogCursor = getLogCursor(env);

    await runSlashCommandWithAutocompleteSelection(page, '/todo delete', title);
    await expectNoDiscordInteractionFailure(page);

    const deleteResponseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expectExecutedSlashCommand(deleteResponseMessage, /todo\s+delete/i);
    await expect(deleteResponseMessage).toContainText(/This todo was deleted\./i);
    await expectInteractionLog('todo delete', deleteLogCursor);
  });
});
