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

test.setTimeout(240_000);

const emoji = {
  options: '\ud83d\udd0e'
};

const defaultSchedule = '0 9 * * *';

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('reminder core flows', () => {
  test('command lifecycle: add, show, pause, resume, and remove', async ({ page }) => {
    const env = readE2EEnv();
    const title = runMarker('e2e reminder command');
    const description = runMarker('e2e reminder command description');

    await createReminderWithCommand(page, title, { description });
    const createdCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expectReminderCard(createdCard, {
      title,
      description,
      status: /active/i,
      result: /Scheduled recurring reminder/i
    });

    await runSlashCommandWithAutocompleteSelection(page, '/reminder show', title);
    await expectNoDiscordInteractionFailure(page);
    const shownCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expectReminderCard(shownCard, {
      title,
      description,
      status: /active/i,
      result: /Showing reminder/i
    });

    await runSlashCommandWithAutocompleteSelection(page, '/reminder pause', title);
    await expectNoDiscordInteractionFailure(page);
    const pausedCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expectReminderCard(pausedCard, {
      title,
      description,
      status: /paused/i,
      result: /Paused reminder/i
    });

    await runSlashCommandWithAutocompleteSelection(page, '/reminder resume', title);
    await expectNoDiscordInteractionFailure(page);
    const resumedCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expectReminderCard(resumedCard, {
      title,
      description,
      status: /active/i,
      result: /Resumed reminder/i
    });

    await runSlashCommandWithAutocompleteSelection(page, '/reminder remove', title);
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, /Deleted reminder/i);

    await runSlashCommand(page, '/reminder list');
    await expectNoDiscordInteractionFailure(page);
    const listMessage = await pinMessageById(page, latestChannelMessage(page, env.channelId));
    await expect(listMessage).toContainText(/Reminders/i, { timeout: 20_000 });
    await expect(listMessage).not.toContainText(title);
  });

  test('private reminder can be listed and managed privately', async ({ page }) => {
    const env = readE2EEnv();
    const title = runMarker('e2e private reminder');
    const description = runMarker('e2e private reminder description');

    await createReminderWithCommand(page, title, {
      description,
      destination: 'private'
    });
    await expect(page.getByText(/only you can see this/i).last()).toBeVisible({
      timeout: 20_000
    });

    const privateCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expectReminderCard(privateCard, {
      title,
      description,
      status: /active/i,
      result: /Scheduled recurring reminder/i
    });
    await expect(privateCard).toContainText(/Destination\s*Private/i);

    await runSlashCommandWithOptions(page, '/reminder list', [
      { name: 'destination', value: 'private' }
    ]);
    await expectNoDiscordInteractionFailure(page);
    const privateList = latestChannelMessage(page, env.channelId);
    await expect(privateList).toContainText(title, { timeout: 20_000 });
    await expect(privateList).toContainText(/Destination:\s*Private option/i);

    await runSlashCommandWithAutocompleteSelection(page, '/reminder pause', title);
    await expectNoDiscordInteractionFailure(page);
    const pausedCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expect(pausedCard).toContainText(/Status\s*paused/i, { timeout: 20_000 });

    await runSlashCommandWithAutocompleteSelection(page, '/reminder resume', title);
    await expectNoDiscordInteractionFailure(page);
    const resumedCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expect(resumedCard).toContainText(/Status\s*active/i, { timeout: 20_000 });

    await runSlashCommandWithAutocompleteSelection(page, '/reminder remove', title);
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, /Deleted reminder/i);
  });

  test('bulk pause and resume all visible reminders', async ({ page }) => {
    const env = readE2EEnv();
    const marker = Date.now().toString(36);
    const firstTitle = `e2e bulk reminder first ${marker}`;
    const secondTitle = `e2e bulk reminder second ${marker}`;

    await createReminderWithCommand(page, firstTitle);
    await expectLatestChannelMessageContaining(page, env.channelId, firstTitle);
    await createReminderWithCommand(page, secondTitle);
    await expectLatestChannelMessageContaining(page, env.channelId, secondTitle);

    await runSlashCommand(page, '/reminder pause all');
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, /Paused \d+ reminders?\./i);

    await runFilteredReminderList(page, {
      search: marker,
      status: 'Paused'
    });
    await expectNoDiscordInteractionFailure(page);
    const pausedList = latestChannelMessage(page, env.channelId);
    await expect(pausedList).toContainText(firstTitle, { timeout: 20_000 });
    await expect(pausedList).toContainText(secondTitle);

    await runSlashCommand(page, '/reminder resume all');
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, /Resumed \d+ reminders?\./i);

    await runFilteredReminderList(page, {
      search: marker,
      status: 'Active'
    });
    await expectNoDiscordInteractionFailure(page);
    const activeList = latestChannelMessage(page, env.channelId);
    await expect(activeList).toContainText(firstTitle, { timeout: 20_000 });
    await expect(activeList).toContainText(secondTitle);

    await runSlashCommandWithAutocompleteSelection(page, '/reminder remove', firstTitle);
    await expectNoDiscordInteractionFailure(page);
    await runSlashCommandWithAutocompleteSelection(page, '/reminder remove', secondTitle);
    await expectNoDiscordInteractionFailure(page);
  });

  test('list options can search and sort descending', async ({ page }) => {
    const env = readE2EEnv();
    const marker = Date.now().toString(36);
    const firstTitle = `e2e sort reminder first ${marker}`;
    const secondTitle = `e2e sort reminder second ${marker}`;

    await createReminderWithCommand(page, firstTitle);
    await expectLatestChannelMessageContaining(page, env.channelId, firstTitle);
    await createReminderWithCommand(page, secondTitle);
    await expectLatestChannelMessageContaining(page, env.channelId, secondTitle);

    await runSlashCommand(page, '/reminder list');
    await expectNoDiscordInteractionFailure(page);
    const listMessage = await pinMessageById(page, latestChannelMessage(page, env.channelId));
    await expect(listMessage).toContainText(/Reminders/i, { timeout: 20_000 });

    await itemActionButton(listMessage, emoji.options).click();
    await fillListOptionsModal(page, {
      sort: 'Descending',
      status: 'All',
      search: marker
    });

    await expect(listMessage).toContainText(firstTitle, { timeout: 20_000 });
    await expect(listMessage).toContainText(secondTitle);
    await expect(listMessage).toContainText(/Sort:\s*Descending/i);
    await expect(listMessage).toContainText(new RegExp(`Search:\\s*${escapeRegExp(marker)}`));
    await expectTextOrder(listMessage, secondTitle, firstTitle);

    await runSlashCommandWithAutocompleteSelection(page, '/reminder remove', firstTitle);
    await expectNoDiscordInteractionFailure(page);
    await runSlashCommandWithAutocompleteSelection(page, '/reminder remove', secondTitle);
    await expectNoDiscordInteractionFailure(page);
  });

  test('invalid reminder id returns a user-facing error', async ({ page }) => {
    await runSlashCommand(page, '/reminder show not-a-real-reminder-id');
    await expectNoDiscordInteractionFailure(page);
    await expect(page.getByText(/That reminder ID is invalid/i).last()).toBeVisible({
      timeout: 20_000
    });
  });
});

async function createReminderWithCommand(
  page: Page,
  title: string,
  options: { description?: string; destination?: string; schedule?: string } = {}
): Promise<void> {
  await startSlashCommand(page, '/reminder add');
  await fillCurrentRequiredSlashOption(page, title);
  await fillCurrentRequiredSlashOption(page, options.schedule ?? defaultSchedule);

  if (options.description) {
    await addSlashTextOption(page, 'description', options.description);
  }
  if (options.destination) {
    await addSlashAutocompleteOption(page, {
      name: 'destination',
      query: options.destination,
      selectionText: new RegExp(`^${escapeRegExp(options.destination)}$`, 'i')
    });
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

async function addSlashAutocompleteOption(
  page: Page,
  input: { name: string; query: string; selectionText: string | RegExp }
): Promise<void> {
  await openSlashCommandOptionsMenu(page);
  await selectSlashOption(page, input.name);

  await page.keyboard.type(input.query, { delay: 20 });
  await page.waitForTimeout(300);
  const selection = page.getByRole('option').filter({ hasText: input.selectionText }).first();
  await expect(selection).toBeVisible({ timeout: 10_000 });
  await selection.click();
  await page.waitForTimeout(300);
}

async function runFilteredReminderList(
  page: Page,
  input: { search: string; status: 'Active' | 'Paused' }
): Promise<void> {
  await runSlashCommandWithAutocompleteOptions(page, '/reminder list', [
    { name: 'status', query: input.status, selectionText: new RegExp(input.status, 'i') }
  ]);

  const env = readE2EEnv();
  const renderedList = await expectLatestChannelMessageContaining(
    page,
    env.channelId,
    /Reminders/i
  );
  const listMessage = await pinMessageById(page, renderedList);
  await itemActionButton(listMessage, emoji.options).click();
  await fillListOptionsModal(page, {
    status: input.status,
    search: input.search
  });
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

async function fillListOptionsModal(
  page: Page,
  options: {
    search: string;
    sort?: 'Ascending' | 'Descending';
    status: 'All' | 'Active' | 'Paused';
  }
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: /View Options/i }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  if (options.sort) {
    await clickModalRadio(dialog, options.sort);
  }
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

async function expectTextOrder(
  locator: Locator,
  firstText: string,
  secondText: string
): Promise<void> {
  const text = await locator.innerText({ timeout: 10_000 });
  const firstIndex = text.indexOf(firstText);
  const secondIndex = text.indexOf(secondText);
  if (firstIndex === -1 || secondIndex === -1 || firstIndex >= secondIndex) {
    throw new Error(`Expected "${firstText}" to appear before "${secondText}".`);
  }
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
