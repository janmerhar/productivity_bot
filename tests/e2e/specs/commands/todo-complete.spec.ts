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

test.describe('/todo complete', () => {
  test('completes an inserted todo selected from the required todo autocomplete', async ({ page }) => {
    const env = readE2EEnv();
    const addLogCursor = getLogCursor(env);
    const title = runMarker('e2e todo complete');

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

    const completeLogCursor = getLogCursor(env);

    await runSlashCommandWithAutocompleteSelection(page, '/todo complete', title);
    await expectNoDiscordInteractionFailure(page);

    const completeResponseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expectExecutedSlashCommand(completeResponseMessage, /todo\s+complete/i);
    await expect(completeResponseMessage).toContainText(/Status\s*Done/);
    await expect(completeResponseMessage).toContainText(/Due\s*Not set/);
    await expect(completeResponseMessage).toContainText(/Assignee\s*None/);
    await expectInteractionLog('todo complete', completeLogCursor);
  });
});
