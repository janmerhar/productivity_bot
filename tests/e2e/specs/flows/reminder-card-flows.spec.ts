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
  sendDiscordMessage,
  startSlashCommand,
  submitSlashCommand
} from '../../support/discord.helpers';

test.setTimeout(240_000);

const emoji = {
  add: '\u2795',
  delete: '\ud83d\uddd1\ufe0f',
  edit: '\u270f\ufe0f',
  options: '\ud83d\udd0e',
  pause: '\u23f8\ufe0f',
  resume: '\u25b6\ufe0f'
};

const defaultSchedule = '0 9 * * *';

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('reminder card flows', () => {
  test('list add, options filter, drilldown, edit, pause, resume, and delete', async ({
    page
  }) => {
    const env = readE2EEnv();
    const activeTitle = runMarker('e2e reminder list active');
    const pausedTitle = runMarker('e2e reminder list paused');
    const editedTitle = runMarker('e2e reminder list edited');
    const editedDescription = runMarker('e2e reminder list edited description');

    await runSlashCommand(page, '/reminder list');
    await expectNoDiscordInteractionFailure(page);

    const listMessage = await pinMessageById(page, latestChannelMessage(page, env.channelId));
    await expect(listMessage).toContainText(/Reminders/i, { timeout: 20_000 });

    await itemActionButton(listMessage, emoji.add).click();
    await fillReminderCreateModal(page, {
      title: activeTitle,
      schedule: defaultSchedule,
      description: runMarker('e2e reminder list active description')
    });
    await expect(listMessage).toContainText(activeTitle, { timeout: 20_000 });

    await createReminderWithCommand(page, pausedTitle, {
      description: runMarker('e2e reminder list paused description')
    });
    await runSlashCommandWithAutocompleteSelection(page, '/reminder pause', pausedTitle);
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, /Paused reminder/i);

    await itemActionButton(listMessage, emoji.options).click();
    await fillListOptionsModal(page, {
      status: 'Paused',
      search: pausedTitle
    });

    await expect(listMessage).toContainText(pausedTitle, { timeout: 20_000 });
    await expect(listMessage).not.toContainText(activeTitle);
    await expect(listMessage).toContainText(/Status:\s*Paused/i);
    await expect(listMessage).toContainText(
      new RegExp(`Search:\\s*${escapeRegExp(formatSearchFilterLabel(pausedTitle))}`)
    );

    await clickNumberButton(listMessage, 1);
    const detailsCard = await expectLatestChannelMessageContaining(page, env.channelId, pausedTitle);
    await expectReminderCard(detailsCard, {
      title: pausedTitle,
      status: /paused/i,
      result: /Showing reminder/i
    });

    await itemActionButton(detailsCard, emoji.edit).click();
    await fillReminderEditModal(page, {
      title: editedTitle,
      schedule: defaultSchedule,
      description: editedDescription
    });
    await expect(detailsCard).toContainText(editedTitle, { timeout: 20_000 });
    await expect(detailsCard).toContainText(editedDescription);

    await itemActionButton(detailsCard, emoji.resume).click();
    await expect(detailsCard).toContainText(/Status\s*active/i, { timeout: 20_000 });
    await expect(detailsCard).toContainText(/Resumed reminder/i);

    await itemActionButton(detailsCard, emoji.pause).click();
    await expect(detailsCard).toContainText(/Status\s*paused/i, { timeout: 20_000 });
    await expect(detailsCard).toContainText(/Paused reminder/i);

    await itemActionButton(detailsCard, emoji.delete).click();
    await confirmModal(page, /Delete Reminder/i);
    await expect(detailsCard).toContainText(/Deleted reminder/i, { timeout: 20_000 });
    await expect(detailsCard).toContainText(/Status\s*missing/i);

    await runSlashCommandWithAutocompleteSelection(page, '/reminder remove', activeTitle);
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, /Deleted reminder/i);
  });

  test('message context menu creates a reminder', async ({ page }) => {
    const env = readE2EEnv();
    const messageText = runMarker('e2e context reminder message');
    const description = runMarker('e2e context reminder description');

    await sendDiscordMessage(page, messageText);
    const sourceMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      messageText
    );

    await runCreateReminderContextMenu(page, sourceMessage);
    await expectDiscordModal(page, /Create Reminder/i);
    await fillReminderCreateModal(page, {
      title: messageText,
      schedule: defaultSchedule,
      description
    });

    const reminderCard = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      messageText
    );
    await expectReminderCard(reminderCard, {
      title: messageText,
      description,
      status: /active/i,
      result: /Scheduled recurring reminder/i
    });

    await itemActionButton(reminderCard, emoji.delete).click();
    await confirmModal(page, /Delete Reminder/i);
    await expect(reminderCard).toContainText(/Deleted reminder/i, { timeout: 20_000 });
  });
});

async function createReminderWithCommand(
  page: Page,
  title: string,
  options: { description?: string; schedule?: string } = {}
): Promise<void> {
  await startSlashCommand(page, '/reminder add');
  await fillCurrentRequiredSlashOption(page, title);
  await fillCurrentRequiredSlashOption(page, options.schedule ?? defaultSchedule);

  if (options.description) {
    await addSlashTextOption(page, 'description', options.description);
  }

  await submitSlashCommand(page);
  await expectNoDiscordInteractionFailure(page);
}

async function fillCurrentRequiredSlashOption(page: Page, value: string): Promise<void> {
  await page.keyboard.type(value, { delay: 20 });
  await page.waitForTimeout(300);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(300);
}

async function addSlashTextOption(
  page: Page,
  optionName: string,
  value: string
): Promise<void> {
  await openSlashCommandOptionsMenu(page);
  await selectSlashOption(page, optionName);

  await page.keyboard.type(value, { delay: 20 });
  await page.waitForTimeout(300);
  await expect(page.locator('[data-slate-editor="true"]').last()).toContainText(value, {
    timeout: 5_000
  });
  await page.keyboard.press('Tab');
  await page.waitForTimeout(300);
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

async function expectReminderCard(
  card: Locator,
  expected: {
    title: string;
    description?: string;
    status: RegExp;
    result?: RegExp;
  }
): Promise<void> {
  await expect(card).toContainText(/Reminder/i);
  await expect(card).toContainText(expected.title);
  await expect(card).toContainText(defaultSchedule);
  await expect(card).toContainText(new RegExp(`Status\\s*${expected.status.source}`, 'i'));
  if (expected.description) {
    await expect(card).toContainText(expected.description);
  }
  if (expected.result) {
    await expect(card).toContainText(expected.result);
  }
}

async function fillReminderCreateModal(
  page: Page,
  input: { title: string; schedule: string; description?: string }
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: /Create Reminder/i }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  const textboxes = dialog.getByRole('textbox');
  await textboxes.nth(0).fill(input.title);
  await textboxes.nth(1).fill(input.schedule);
  if (input.description !== undefined) {
    await textboxes.nth(2).fill(input.description);
  }

  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function fillReminderEditModal(
  page: Page,
  input: { title: string; schedule: string; description?: string }
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: /Edit Reminder/i }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  const textboxes = dialog.getByRole('textbox');
  await textboxes.nth(0).fill(input.schedule);
  await textboxes.nth(1).fill(input.title);
  if (input.description !== undefined) {
    await textboxes.nth(2).fill(input.description);
  }

  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function fillListOptionsModal(
  page: Page,
  options: {
    search: string;
    status: 'All' | 'Active' | 'Paused';
  }
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: /View Options/i }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  await clickModalRadio(dialog, options.status);
  await dialog.getByRole('textbox').first().fill(options.search);
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

async function clickNumberButton(message: Locator, number: number): Promise<void> {
  const button = accessoryRoot(message).getByRole('button', {
    name: String(number),
    exact: true
  });
  await expect(button).toBeEnabled({ timeout: 10_000 });
  await button.click();
}

async function runCreateReminderContextMenu(page: Page, message: Locator): Promise<void> {
  await message.click({ button: 'right' });

  const directItem = createReminderContextMenuItem(page);
  if (await isVisible(directItem)) {
    await directItem.click();
    return;
  }

  const appsItem = page.getByRole('menuitem').filter({ hasText: /Apps/i }).last();
  await expect(appsItem).toBeVisible({ timeout: 10_000 });
  await appsItem.hover();

  let createReminderItem = createReminderContextMenuItem(page);
  if (!(await isVisible(createReminderItem))) {
    await appsItem.click();
    createReminderItem = createReminderContextMenuItem(page);
  }

  if (!(await isVisible(createReminderItem))) {
    const botSubmenuItem = reminderBotContextMenuItem(page);
    await expect(botSubmenuItem).toBeVisible({ timeout: 10_000 });
    await botSubmenuItem.hover();
    createReminderItem = createReminderContextMenuItem(page);
    if (!(await isVisible(createReminderItem))) {
      await botSubmenuItem.click();
      createReminderItem = createReminderContextMenuItem(page);
    }
  }

  await expect(createReminderItem).toBeVisible({ timeout: 10_000 });
  await createReminderItem.click();
}

function createReminderContextMenuItem(page: Page): Locator {
  return page.getByRole('menuitem').filter({ hasText: /Create Reminder/i }).last();
}

function reminderBotContextMenuItem(page: Page): Locator {
  const botName = readE2EEnv().botName?.trim();
  const botPattern = botName ? new RegExp(escapeRegExp(botName), 'i') : /productivity_bot/i;
  return page.getByRole('menuitem').filter({ hasText: botPattern }).last();
}

function itemActionButton(message: Locator, emojiText: string): Locator {
  return accessoryRoot(message)
    .locator(`button:has(img.emoji[alt="${cssString(emojiText)}"])`)
    .first();
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

function formatSearchFilterLabel(value: string): string {
  const text = value.trim();
  return text.length <= 24 ? text : `${text.slice(0, 21).trimEnd()}...`;
}
