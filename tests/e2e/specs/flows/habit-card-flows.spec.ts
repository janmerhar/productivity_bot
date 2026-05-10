import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  ensureAuthStateExists,
  expectDiscordModal,
  expectLatestChannelMessageContaining,
  expectNoDiscordInteractionFailure,
  latestChannelMessage,
  openDiscordTestChannel,
  openSlashCommandOptionsMenu,
  readE2EEnv,
  runMarker,
  runSlashCommand,
  runSlashCommandWithAutocompleteSelection,
  runSlashCommandWithOptions,
  startSlashCommand,
  submitSlashCommand
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });
test.setTimeout(240_000);

const emoji = {
  add: '\u2795',
  options: '\ud83d\udd0e'
};

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('habit card flows', () => {
  test('list add, options filter, drilldown, edit, mark, and delete', async ({ page }) => {
    const env = readE2EEnv();
    const activeTitle = runMarker('e2e habit list active');
    const activeDescription = runMarker('e2e habit list active description');
    const skippedTitle = runMarker('e2e habit list skipped');
    const skippedDescription = runMarker('e2e habit list skipped description');
    const editedTitle = runMarker('e2e habit list edited');
    const editedDescription = runMarker('e2e habit list edited description');

    await runSlashCommand(page, '/habit list');
    await expectNoDiscordInteractionFailure(page);

    let listMessage = await pinMessageById(page, latestChannelMessage(page, env.channelId));
    await expect(listMessage).toContainText(/Habits/i, { timeout: 20_000 });

    await itemActionButton(listMessage, emoji.add).click();
    await fillHabitModal(page, {
      title: activeTitle,
      description: activeDescription,
      modalTitle: /Add Habit/i
    });
    await expect(listMessage).toContainText(activeTitle, { timeout: 20_000 });

    await runSlashCommandWithOptions(page, `/habit add ${skippedTitle}`, [
      { name: 'description', value: skippedDescription }
    ]);
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, skippedTitle);

    await runHabitMarkCommand(page, skippedTitle, 'Skip');
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, skippedTitle);

    await runSlashCommand(page, '/habit list');
    await expectNoDiscordInteractionFailure(page);
    listMessage = await pinMessageById(page, latestChannelMessage(page, env.channelId));
    await expect(listMessage).toContainText(/Habits/i, { timeout: 20_000 });

    await expect(itemActionButton(listMessage, emoji.options)).toBeEnabled({
      timeout: 10_000
    });
    await itemActionButton(listMessage, emoji.options).click();
    await fillListOptionsModal(page, {
      sort: 'Descending',
      status: 'Skipped'
    });

    await expect(listMessage).toContainText(skippedTitle, { timeout: 20_000 });
    await expect(listMessage).not.toContainText(activeTitle);
    await expect(listMessage).toContainText(/Status:\s*Skipped/i);
    await expect(listMessage).toContainText(/Sort:\s*Descending/i);

    await clickNumberButton(listMessage, 1);
    const detailsCard = await expectLatestHabitDetailsCardContaining(
      page,
      env.channelId,
      skippedTitle,
      /Skip/i
    );
    await expectHabitCard(detailsCard, {
      title: skippedTitle,
      description: skippedDescription,
      status: /Skip/i
    });

    await habitCardButton(detailsCard, 'edit').click();
    await fillHabitModal(page, {
      title: editedTitle,
      description: editedDescription,
      modalTitle: /Edit Habit/i
    });
    await expectHabitCard(detailsCard, {
      title: editedTitle,
      description: editedDescription,
      status: /Skip/i
    });

    await habitCardButton(detailsCard, 'complete').click();
    await expect(detailsCard).toContainText(/Today:\s*Complete/i, { timeout: 20_000 });
    await expect(habitCardButton(detailsCard, 'complete')).toBeDisabled({
      timeout: 10_000
    });

    await habitCardButton(detailsCard, 'skip').click();
    await expect(detailsCard).toContainText(/Today:\s*Skip/i, { timeout: 20_000 });
    await expect(habitCardButton(detailsCard, 'skip')).toBeDisabled({
      timeout: 10_000
    });

    await habitCardButton(detailsCard, 'delete').click();
    await confirmModal(page, /Delete/i);
    await expect(detailsCard).toContainText(/This habit was deleted\./i, {
      timeout: 20_000
    });
    await expect(accessoryRoot(detailsCard).locator('button')).toHaveCount(0);

    await runSlashCommandWithAutocompleteSelection(page, '/habit delete', activeTitle);
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, /This habit was deleted\./i);
  });

  test('detail card can create another habit', async ({ page }) => {
    const env = readE2EEnv();
    const sourceTitle = runMarker('e2e habit card source');
    const followupTitle = runMarker('e2e habit card followup');
    const followupDescription = runMarker('e2e habit card followup description');

    await runSlashCommand(page, `/habit add ${sourceTitle}`);
    await expectNoDiscordInteractionFailure(page);

    const sourceCard = await pinMessageById(
      page,
      await expectLatestChannelMessageContaining(page, env.channelId, sourceTitle)
    );
    await expectHabitCard(sourceCard, {
      title: sourceTitle,
      status: /Not set/i
    });

    await habitCardButton(sourceCard, 'add').click();
    await fillHabitModal(page, {
      title: followupTitle,
      description: followupDescription,
      modalTitle: /Add Habit/i
    });

    const followupCard = await pinMessageById(
      page,
      await expectLatestChannelMessageContaining(page, env.channelId, followupTitle)
    );
    await expectHabitCard(followupCard, {
      title: followupTitle,
      description: followupDescription,
      status: /Not set/i
    });

    await habitCardButton(followupCard, 'delete').click();
    await confirmModal(page, /Delete/i);
    await expect(followupCard).toContainText(/This habit was deleted\./i, {
      timeout: 20_000
    });

    await habitCardButton(sourceCard, 'delete').click();
    await confirmModal(page, /Delete/i);
    await expect(sourceCard).toContainText(/This habit was deleted\./i, {
      timeout: 20_000
    });
  });
});

async function fillHabitModal(
  page: Page,
  input: { title: string; description?: string; modalTitle: string | RegExp }
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: input.modalTitle }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  const textboxes = dialog.getByRole('textbox');
  await textboxes.nth(0).fill(input.title);
  if (input.description !== undefined) {
    await textboxes.nth(1).fill(input.description);
  }

  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
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

async function fillListOptionsModal(
  page: Page,
  input: { sort: 'Ascending' | 'Descending'; status: 'All' | 'Incomplete' | 'Skipped' }
): Promise<void> {
  await expectDiscordModal(page, /View Options/i);
  const dialog = page.getByRole('dialog').filter({ hasText: /View Options/i }).last();

  await clickModalRadio(dialog, input.sort);
  await clickModalRadio(dialog, input.status);
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function clickModalRadio(dialog: Locator, label: string): Promise<void> {
  const visibleLabel = dialog.getByText(new RegExp(`^${escapeRegExp(label)}$`, 'i')).last();
  if (await isVisible(visibleLabel)) {
    await visibleLabel.click({ force: true });
    return;
  }

  const radio = dialog.getByRole('radio', {
    name: new RegExp(`^${escapeRegExp(label)}$`, 'i')
  });
  if (await isVisible(radio)) {
    await radio.click({ force: true });
    return;
  }

  throw new Error(`Could not select modal radio "${label}".`);
}

async function confirmModal(page: Page, modalTitle: string | RegExp): Promise<void> {
  await expectDiscordModal(page, modalTitle);
  const dialog = page.getByRole('dialog').filter({ hasText: modalTitle }).last();
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function expectHabitCard(
  card: Locator,
  expected: { title: string; description?: string; status: RegExp }
): Promise<void> {
  await expect(card).toContainText(expected.title, { timeout: 20_000 });
  await expect(card).toContainText(new RegExp(`Today:\\s*${expected.status.source}`, 'i'), {
    timeout: 20_000
  });
  if (expected.description) {
    await expect(card).toContainText(expected.description);
  }
}

async function expectLatestHabitDetailsCardContaining(
  page: Page,
  channelId: string,
  text: string,
  status: RegExp
): Promise<Locator> {
  const message = page
    .locator(`li[id^="chat-messages-${channelId}-"]`)
    .filter({ hasText: text })
    .filter({ hasText: new RegExp(`Today:\\s*${status.source}`, 'i') })
    .filter({ hasNotText: /Habits -|Marked/i })
    .last();
  await expect(message).toBeVisible({ timeout: 20_000 });
  await expect(message).toContainText(text, { timeout: 20_000 });
  return pinMessageById(page, message);
}

async function clickNumberButton(message: Locator, number: number): Promise<void> {
  const button = accessoryRoot(message).getByRole('button', {
    name: String(number),
    exact: true
  });
  await expect(button).toBeEnabled({ timeout: 10_000 });
  await button.click();
}

function itemActionButton(message: Locator, emojiText: string): Locator {
  return accessoryRoot(message)
    .locator(`button:has(img.emoji[alt="${cssString(emojiText)}"])`)
    .first();
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
