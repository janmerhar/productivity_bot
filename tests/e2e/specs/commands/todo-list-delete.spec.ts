import { expect, test } from '@playwright/test';
import {
  ensureAuthStateExists,
  expectDiscordModal,
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

test.describe('/todo list delete', () => {
  test('deletes a custom todo list selected from the required list autocomplete', async ({ page }) => {
    const env = readE2EEnv();
    const createLogCursor = getLogCursor(env);
    const listName = runMarker('e2e todo list delete');

    await runSlashCommand(page, `/todo list create ${listName}`);
    await expectNoDiscordInteractionFailure(page);

    const createMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      listName
    );
    await expectExecutedSlashCommand(createMessage, /todo\s+list\s+create/i);
    await expect(createMessage).toContainText(/Todo List Created/i);
    await expect(createMessage).toContainText(/Items:\s*0/i);
    await expectInteractionLog('todo list create', createLogCursor);

    const deleteLogCursor = getLogCursor(env);

    await runSlashCommandWithAutocompleteSelection(page, '/todo list delete', listName);
    await expectDiscordModal(page, /Delete Todo List/i);

    const dialog = page.getByRole('dialog').filter({ hasText: /Delete Todo List/i }).last();
    await expect(dialog).toContainText(listName);
    await expect(dialog).toContainText(/Current items:\s*0/i);
    await dialog.getByRole('button', { name: /submit/i }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
    await expectNoDiscordInteractionFailure(page);

    await expectInteractionLog('todo list delete', deleteLogCursor);

    await runSlashCommand(page, '/todo list browse');
    await expectNoDiscordInteractionFailure(page);

    const directoryMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      /Todo List Directory/i
    );
    await expect(directoryMessage).not.toContainText(listName);
  });
});
