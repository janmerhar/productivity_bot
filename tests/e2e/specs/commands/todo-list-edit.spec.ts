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
  runSlashCommandWithAutocompleteSelectionsAndText
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('/todo list edit', () => {
  test('renames a custom todo list selected from the required list autocomplete', async ({ page }) => {
    const env = readE2EEnv();
    const createLogCursor = getLogCursor(env);
    const originalName = runMarker('e2e todo list edit');
    const updatedName = runMarker('e2e todo list edited');

    await runSlashCommand(page, `/todo list create ${originalName}`);
    await expectNoDiscordInteractionFailure(page);

    const createMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      originalName
    );
    await expectExecutedSlashCommand(createMessage, /todo\s+list\s+create/i);
    await expect(createMessage).toContainText(/Todo List Created/i);
    await expect(createMessage).toContainText(/Items:\s*0/i);
    await expectInteractionLog('todo list create', createLogCursor);

    const editLogCursor = getLogCursor(env);

    await runSlashCommandWithAutocompleteSelectionsAndText(
      page,
      '/todo list edit',
      [{ query: originalName }],
      updatedName
    );
    await expectNoDiscordInteractionFailure(page);

    const editMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      updatedName
    );
    await expectExecutedSlashCommand(editMessage, /todo\s+list\s+edit/i);
    await expect(editMessage).toContainText(/Todo List Updated/i);
    await expect(editMessage).toContainText(/Previous name/i);
    await expect(editMessage).toContainText(originalName);
    await expect(editMessage).toContainText(/New name/i);
    await expect(editMessage).toContainText(updatedName);
    await expectInteractionLog('todo list edit', editLogCursor);
  });
});
