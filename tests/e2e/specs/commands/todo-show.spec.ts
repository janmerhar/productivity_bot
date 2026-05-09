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

test.describe('/todo show', () => {
  test('shows an inserted todo selected from the required todo autocomplete', async ({ page }) => {
    const env = readE2EEnv();
    const addLogCursor = getLogCursor(env);
    const title = runMarker('e2e todo show');

    await runSlashCommand(page, `/todo add ${title}`);
    await expectNoDiscordInteractionFailure(page);

    const addResponseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expectTodoItemResponse(addResponseMessage, /todo\s+add/i);
    await expectInteractionLog('todo add', addLogCursor);

    const showLogCursor = getLogCursor(env);

    await runSlashCommandWithAutocompleteSelection(page, '/todo show', title);
    await expectNoDiscordInteractionFailure(page);

    const showResponseMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expectTodoItemResponse(showResponseMessage, /todo\s+show/i);
    await expectInteractionLog('todo show', showLogCursor);
  });
});

async function expectTodoItemResponse(
  responseMessage: Locator,
  commandName: RegExp
): Promise<void> {
  await expectExecutedSlashCommand(responseMessage, commandName);
  await expect(responseMessage).toContainText(/Status\s*To Do/);
  await expect(responseMessage).toContainText(/Due\s*Not set/);
  await expect(responseMessage).toContainText(/Assignee\s*None/);
}
