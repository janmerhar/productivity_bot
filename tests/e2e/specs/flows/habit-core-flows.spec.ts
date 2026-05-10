import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  ensureAuthStateExists,
  expectLatestChannelMessageContaining,
  expectNoDiscordInteractionFailure,
  latestChannelMessage,
  openDiscordTestChannel,
  openSlashCommandOptionsMenu,
  readE2EEnv,
  runMarker,
  runSlashCommand,
  runSlashCommandWithAutocompleteOptions,
  runSlashCommandWithAutocompleteSelection,
  runSlashCommandWithOptions,
  startSlashCommand,
  submitSlashCommand
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });
test.setTimeout(240_000);

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('habit core flows', () => {
  test('command lifecycle: add, show, mark, list, and delete', async ({ page }) => {
    const env = readE2EEnv();
    const title = runMarker('e2e habit command');
    const description = runMarker('e2e habit command description');

    await runSlashCommandWithOptions(page, `/habit add ${title}`, [
      { name: 'description', value: description }
    ]);
    await expectNoDiscordInteractionFailure(page);

    const createdCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expectHabitCard(createdCard, {
      title,
      description,
      status: /Not set/i
    });

    await runSlashCommandWithAutocompleteSelection(page, '/habit show', title);
    await expectNoDiscordInteractionFailure(page);
    const shownCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expectHabitCard(shownCard, {
      title,
      description,
      status: /Not set/i
    });

    await runHabitMarkCommand(page, title, 'Skip');
    await expectNoDiscordInteractionFailure(page);

    const skippedCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expect(skippedCard).toContainText(/Marked/i);
    await expectHabitCard(skippedCard, {
      title,
      description,
      status: /Skip/i
    });

    await runSlashCommandWithAutocompleteOptions(page, '/habit list', [
      { name: 'status', query: 'Skipped', selectionText: /Skipped/i },
      { name: 'sort', query: 'Descending', selectionText: /Descending/i }
    ]);
    await expectNoDiscordInteractionFailure(page);

    const skippedList = latestChannelMessage(page, env.channelId);
    await expect(skippedList).toContainText(/Habits/i, { timeout: 20_000 });
    await expect(skippedList).toContainText(title);
    await expect(skippedList).toContainText(/Status:\s*Skipped/i);
    await expect(skippedList).toContainText(/Sort:\s*Descending/i);

    await runHabitMarkCommand(page, title, 'Complete');
    await expectNoDiscordInteractionFailure(page);

    const completedCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expectHabitCard(completedCard, {
      title,
      description,
      status: /Complete/i
    });

    await runSlashCommandWithAutocompleteSelection(page, '/habit delete', title);
    await expectNoDiscordInteractionFailure(page);
    const deletedCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expect(deletedCard).toContainText(/This habit was deleted\./i);
  });

  test('personal habit can be created, listed privately, and deleted from its card', async ({
    page
  }) => {
    const env = readE2EEnv();
    const title = runMarker('e2e personal habit');

    await runSlashCommandWithAutocompleteOptions(page, `/habit add ${title}`, [
      { name: 'destination', query: 'Personal', selectionText: /Personal/i }
    ]);
    await expectNoDiscordInteractionFailure(page);
    await expect(page.getByText(/only you can see this/i).last()).toBeVisible({
      timeout: 20_000
    });

    const personalCard = await pinMessageById(
      page,
      await expectLatestChannelMessageContaining(page, env.channelId, title)
    );
    await expectHabitCard(personalCard, {
      title,
      status: /Not set/i
    });

    await runSlashCommandWithAutocompleteOptions(page, '/habit list', [
      { name: 'scope', query: 'Personal', selectionText: /Personal/i }
    ]);
    await expectNoDiscordInteractionFailure(page);
    const personalList = latestChannelMessage(page, env.channelId);
    await expect(personalList).toContainText(title, { timeout: 20_000 });
    await expect(personalList).toContainText(/Habits - Personal/i);

    await habitCardButton(personalCard, 'delete').click();
    await confirmHabitDeleteModal(page, /Delete/i);

    await runSlashCommandWithAutocompleteOptions(page, '/habit list', [
      { name: 'scope', query: 'Personal', selectionText: /Personal/i }
    ]);
    await expectNoDiscordInteractionFailure(page);
    const refreshedPersonalList = latestChannelMessage(page, env.channelId);
    await expect(refreshedPersonalList).toContainText(/Habits - Personal/i, {
      timeout: 20_000
    });
    await expect(refreshedPersonalList).not.toContainText(title);
  });
});

async function expectHabitCard(
  card: Locator,
  expected: { title: string; description?: string; status: RegExp }
): Promise<void> {
  await expect(card).toContainText(expected.title);
  await expect(card).toContainText(new RegExp(`Today:\\s*${expected.status.source}`, 'i'));
  if (expected.description) {
    await expect(card).toContainText(expected.description);
  }
}

async function runHabitMarkCommand(
  page: Page,
  habitTitle: string,
  status: 'Complete' | 'Skip' | 'Incomplete'
): Promise<void> {
  await startSlashCommand(page, '/habit mark');
  await selectCurrentAutocompleteOption(page, habitTitle);
  await addSlashAutocompleteOption(page, {
    name: 'status',
    query: status,
    selectionText: new RegExp(`^${escapeRegExp(status)}$`, 'i')
  });
  await submitSlashCommand(page);
}

async function selectCurrentAutocompleteOption(
  page: Page,
  query: string,
  selectionText: string | RegExp = query
): Promise<void> {
  await page.keyboard.type(query, { delay: 20 });
  await page.waitForTimeout(300);

  const selectionPattern =
    typeof selectionText === 'string'
      ? new RegExp(escapeRegExp(selectionText), 'i')
      : selectionText;
  const selection = page.getByRole('option').filter({ hasText: selectionPattern }).first();
  await expect(selection).toBeVisible({ timeout: 10_000 });
  await selection.click();
  await page.waitForTimeout(300);
}

async function addSlashAutocompleteOption(
  page: Page,
  input: { name: string; query: string; selectionText: string | RegExp }
): Promise<void> {
  await openSlashCommandOptionsMenu(page);
  await selectSlashOption(page, input.name);
  await selectCurrentAutocompleteOption(page, input.query, input.selectionText);
}

async function selectSlashOption(page: Page, optionName: string): Promise<void> {
  await page.keyboard.type(optionName, { delay: 20 });
  await page.waitForTimeout(300);

  const optionPattern = new RegExp(`^${escapeRegExp(optionName)}\\b`, 'i');
  const option = page.getByRole('option').filter({ hasText: optionPattern }).first();
  if (await isVisible(option)) {
    await option.click();
  } else {
    await page.keyboard.press('Enter');
  }

  await expect(slashOptionKey(page, optionName)).toBeVisible({ timeout: 5_000 });
}

function slashOptionKey(page: Page, optionName: string): Locator {
  return page
    .locator('[class*="optionPillKey"]')
    .filter({ hasText: new RegExp(`\\b${escapeRegExp(optionName)}\\b`, 'i') })
    .last();
}

async function confirmHabitDeleteModal(
  page: Page,
  modalTitle: string | RegExp
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: modalTitle }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

function habitCardButton(
  message: Locator,
  action: 'complete' | 'skip' | 'add' | 'edit' | 'delete'
): Locator {
  const indexes = {
    complete: 0,
    skip: 1,
    add: 2,
    edit: 3,
    delete: 4
  };
  return accessoryRoot(message).locator('button').nth(indexes[action]);
}

function accessoryRoot(message: Locator): Locator {
  return message.locator('[id^="message-accessories-"]').first();
}

async function pinMessageById(page: Page, message: Locator): Promise<Locator> {
  const messageId = await message.getAttribute('id');
  if (!messageId) {
    throw new Error('Could not pin Discord message because it had no id.');
  }

  return page.locator(`li[id="${cssString(messageId)}"]`);
}

async function isVisible(locator: Locator): Promise<boolean> {
  try {
    return await locator.isVisible({ timeout: 1_000 });
  } catch {
    return false;
  }
}

function cssString(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
