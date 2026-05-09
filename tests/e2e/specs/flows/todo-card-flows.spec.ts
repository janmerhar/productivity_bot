import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  ensureAuthStateExists,
  expectDiscordModal,
  expectLatestChannelMessageContaining,
  expectNoDiscordInteractionFailure,
  latestChannelMessage,
  openDiscordTestChannel,
  readE2EEnv,
  runMarker,
  runSlashCommand,
  runSlashCommandWithAutocompleteOptions,
  runSlashCommandWithOptions,
  sendDiscordMessage
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });
test.setTimeout(240_000);

const emoji = {
  add: '\u2795',
  assign: '\ud83d\udc65',
  clear: '\ud83e\uddf9',
  complete: '\u2705',
  delete: '\ud83d\uddd1\ufe0f',
  edit: '\u270f\ufe0f',
  listShow: '\ud83d\udccb',
  next: '\u25b6\ufe0f',
  options: '\ud83d\udd0e',
  progress: '\ud83d\udfe1'
};

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('todo card flows', () => {
  test('delete from item card', async ({ page }) => {
    const env = readE2EEnv();
    const title = runMarker('e2e card delete');

    await runSlashCommand(page, `/todo add ${title}`);
    await expectNoDiscordInteractionFailure(page);

    const itemCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await itemActionButton(itemCard, emoji.delete).click();
    await confirmModal(page, /Delete/i);

    await expect(itemCard).toContainText(/This todo was deleted\./i, { timeout: 20_000 });
    await expect(accessoryRoot(itemCard).locator('button')).toHaveCount(0);

    await runSlashCommand(page, '/todo list show');
    await expectNoDiscordInteractionFailure(page);
    const listMessage = latestChannelMessage(page, env.channelId);
    await expect(listMessage).toContainText(/Tasks/i, { timeout: 20_000 });
    await expect(listMessage).not.toContainText(title);
  });

  test('assign and unassign from item card', async ({ page }) => {
    const env = readE2EEnv();
    const title = runMarker('e2e card assign');

    await runSlashCommand(page, `/todo add ${title}`);
    await expectNoDiscordInteractionFailure(page);

    const itemCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await assignFromCard(page, itemCard, 'Me');
    await expect(itemCard).toContainText(/Assignee/i, { timeout: 20_000 });
    await expect(itemCard).not.toContainText(/Assignee\s*None/i);

    await assignFromCard(page, itemCard, 'None');
    await expect(itemCard).toContainText(/Assignee\s*None/i, { timeout: 20_000 });
  });

  test('custom list lifecycle from list card', async ({ page }) => {
    const env = readE2EEnv();
    const listName = runMarker('e2e lifecycle list');
    const renamedListName = runMarker('e2e lifecycle renamed');
    const title = runMarker('e2e lifecycle item');

    const listCard = await createTodoList(page, listName);

    await itemActionButton(listCard, emoji.edit).click();
    await fillSingleFieldModal(page, /Rename Todo List/i, renamedListName);
    await expect(listCard).toContainText(renamedListName, { timeout: 20_000 });

    await itemActionButton(listCard, emoji.add).click();
    await fillTodoModal(page, title, /Add to/i);
    const createdItemCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expect(createdItemCard).toContainText(renamedListName);

    await itemActionButton(listCard, emoji.listShow).click();
    const listItemsMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expect(listItemsMessage).toContainText(renamedListName);

    await itemActionButton(listCard, emoji.clear).click();
    await confirmModal(page, /Clear Todo List/i);
    await expect(listCard).toContainText(/Todo List Cleared/i, { timeout: 20_000 });
    await expect(listCard).toContainText(/Removed items:\s*`?1`?/i);

    await itemActionButton(listCard, emoji.delete).click();
    await confirmModal(page, /Delete Todo List/i);
    await expect(listCard).toContainText(/Todo List Deleted/i, { timeout: 20_000 });
    await expect(listCard).toContainText(/Removed items:\s*`?0`?/i);
  });

  test('overview cross-list item drilldown', async ({ page }) => {
    const env = readE2EEnv();
    const marker = Date.now().toString(36);
    const channelTitle = `overview-channel-${marker}`;
    const customTitle = `overview-custom-${marker}`;
    const listName = `aaa overview-list-${marker}`;

    await runSlashCommand(page, `/todo add ${channelTitle}`);
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, channelTitle);

    const customListCard = await createTodoList(page, listName);
    await itemActionButton(customListCard, emoji.add).click();
    await fillTodoModal(page, customTitle, /Add to/i);
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, customTitle);

    await showOverviewDescending(page);
    const overviewMessage = latestChannelMessage(page, env.channelId);
    await expect(overviewMessage).toContainText(channelTitle, { timeout: 20_000 });
    await expect(overviewMessage).toContainText(customTitle);

    await clickNumberButton(overviewMessage, 1);
    const detailsCard = await expectLatestItemCardContaining(page, env.channelId, customTitle);
    await completeItemFromCard(detailsCard);

    await showOverviewDescending(page);
    const refreshedOverview = latestChannelMessage(page, env.channelId);
    await expect(refreshedOverview).toContainText(
      new RegExp(`${escapeRegExp(customTitle)}[\\s\\S]*\\[Done\\]`),
      { timeout: 20_000 }
    );
  });

  test('personal todo flow', async ({ page }) => {
    const env = readE2EEnv();
    const title = runMarker('e2e personal item');
    const editedTitle = runMarker('e2e personal edited');

    await runSlashCommandWithOptions(page, `/todo add ${title}`, [
      { name: 'list', value: 'personal' }
    ]);
    await expectNoDiscordInteractionFailure(page);
    await expect(page.getByText(/only you can see this/i).last()).toBeVisible({
      timeout: 20_000
    });

    const personalCard = await expectLatestItemCardContaining(page, env.channelId, title);
    await expect(personalCard).toContainText(/Personal/i);

    await showPersonalTodoList(page);
    const personalList = latestChannelMessage(page, env.channelId);
    await expectListMessageContains(page, personalList, title);
    await expect(page.getByText(/only you can see this/i).last()).toBeVisible();

    await itemCardActionButton(personalCard, 0).click();
    await fillTodoModal(page, editedTitle, /Edit/i);
    await expect(personalCard).toContainText(editedTitle, { timeout: 20_000 });
    await completeItemFromCard(personalCard);
  });

  test('context menu todo', async ({ page }) => {
    const env = readE2EEnv();
    const messageText = runMarker('e2e context todo message');

    await sendDiscordMessage(page, messageText);
    const sourceMessage = await pinMessageById(
      page,
      await expectLatestChannelMessageContaining(
        page,
        env.channelId,
        messageText
      )
    );
    const spacerText = runMarker('e2e context spacer');
    await sendDiscordMessage(page, spacerText);
    await expectLatestChannelMessageContaining(page, env.channelId, spacerText);

    await runAddToTodoContextMenu(page, sourceMessage, messageText);
    await expectNoDiscordInteractionFailure(page);

    const itemCard = await expectLatestChannelMessageContaining(page, env.channelId, messageText);
    await expect(itemCard).toContainText(/Status\s*To Do/i);
    await completeItemFromCard(itemCard);
  });
});

async function createTodoList(page: Page, listName: string): Promise<Locator> {
  const env = readE2EEnv();
  await runSlashCommand(page, `/todo list create ${listName}`);
  await expectNoDiscordInteractionFailure(page);
  const listCard = await expectLatestChannelMessageContaining(page, env.channelId, listName);
  return pinMessageById(page, listCard);
}

async function expectLatestItemCardContaining(
  page: Page,
  channelId: string,
  text: string | RegExp
): Promise<Locator> {
  const message = page
    .locator(`li[id^="chat-messages-${channelId}-"]`)
    .filter({ hasText: text })
    .filter({ hasText: /Status/i })
    .filter({ hasText: /Due/i })
    .last();
  await expect(message).toBeVisible({ timeout: 20_000 });
  await expect(message).toContainText(text, { timeout: 20_000 });
  return pinMessageById(page, message);
}

async function showTodoList(
  page: Page,
  listName: string,
  selectionText: string | RegExp = listName
): Promise<void> {
  await runSlashCommandWithAutocompleteOptions(page, '/todo list show', [
    { name: 'list', query: listName, selectionText }
  ]);
  await expectNoDiscordInteractionFailure(page);
}

async function showPersonalTodoList(page: Page): Promise<void> {
  await runSlashCommandWithOptions(page, '/todo list show', [
    { name: 'list', value: 'personal' }
  ]);
  await expectNoDiscordInteractionFailure(page);
}

async function expectListMessageContains(
  page: Page,
  message: Locator,
  text: string
): Promise<void> {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    if (await locatorContainsText(message, text)) {
      return;
    }

    const nextButton = itemActionButton(message, emoji.next);
    if (!(await isVisible(nextButton)) || (await nextButton.isDisabled())) {
      break;
    }

    try {
      await nextButton.click({ timeout: 5_000 });
    } catch (error) {
      if (await locatorContainsText(message, text)) {
        return;
      }
      if (await nextButton.isDisabled()) {
        break;
      }
      throw error;
    }
    await page.waitForTimeout(1_000);
  }

  await expect(message).toContainText(text, { timeout: 2_000 });
}

async function showOverviewDescending(page: Page): Promise<void> {
  await runSlashCommandWithAutocompleteOptions(page, '/todo overview', [
    { name: 'sort', query: 'Descending', selectionText: /Descending/i }
  ]);
  await expectNoDiscordInteractionFailure(page);
}

async function fillTodoModal(
  page: Page,
  title: string,
  modalTitle: string | RegExp
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: modalTitle }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByRole('textbox').first().fill(title);
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function fillSingleFieldModal(
  page: Page,
  modalTitle: string | RegExp,
  value: string
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: modalTitle }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByRole('textbox').first().fill(value);
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function confirmModal(page: Page, modalTitle: string | RegExp): Promise<void> {
  await expectDiscordModal(page, modalTitle);
  const dialog = page.getByRole('dialog').filter({ hasText: modalTitle }).last();
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function assignFromCard(
  page: Page,
  card: Locator,
  assigneeLabel: 'Me' | 'None'
): Promise<void> {
  await itemActionButton(card, emoji.assign).click();

  const dialog = page.getByRole('dialog').filter({ hasText: /Assign/i }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await selectOption(page, dialog, assigneeLabel);
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function selectOption(
  page: Page,
  root: Locator,
  optionLabel: string
): Promise<void> {
  const select = root
    .getByRole('combobox')
    .or(root.getByRole('button').filter({ hasText: /^(None|Me)\b/i }))
    .last();
  await expect(select).toBeVisible({ timeout: 10_000 });
  await select.click();
  const option = page
    .getByRole('option')
    .or(page.getByRole('menuitem'))
    .filter({ hasText: new RegExp(`^${escapeRegExp(optionLabel)}\\b`, 'i') })
    .first();
  await expect(option).toBeVisible({ timeout: 10_000 });
  await option.click({ force: true });
}

async function filterListSearch(
  page: Page,
  listMessage: Locator,
  searchText: string
): Promise<void> {
  await itemActionButton(listMessage, emoji.options).click();
  const dialog = page.getByRole('dialog').filter({ hasText: /View Options/i }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByRole('textbox').first().fill(searchText);
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
  await expect(listMessage).toContainText(searchText, { timeout: 20_000 });
}

async function completeItemFromCard(card: Locator): Promise<void> {
  await itemCardActionButton(card, 1).click();
  await expect(card).toContainText(/Status\s*In Progress/, { timeout: 20_000 });
  await itemCardActionButton(card, 1).click();
  await expect(card).toContainText(/Status\s*Done/, { timeout: 20_000 });
  await expect(itemCardActionButton(card, 1)).toBeDisabled({ timeout: 10_000 });
}

async function clickNumberButton(message: Locator, number: number): Promise<void> {
  const button = accessoryRoot(message).getByRole('button', {
    name: String(number),
    exact: true
  });
  await expect(button).toBeEnabled({ timeout: 10_000 });
  await button.click();
}

async function runAddToTodoContextMenu(
  page: Page,
  message: Locator,
  messageText?: string
): Promise<void> {
  const target = messageText ? page.getByText(messageText).last() : message;
  await target.click({ button: 'right', timeout: 10_000 });

  const directItem = page.getByRole('menuitem').filter({ hasText: /^Add to Todo$/i }).last();
  if (await isVisible(directItem)) {
    await directItem.click();
    return;
  }

  const appsItem = page.getByRole('menuitem').filter({ hasText: /Apps/i }).last();
  await expect(appsItem).toBeVisible({ timeout: 10_000 });
  let addToTodoItem = page.getByRole('menuitem').filter({ hasText: /^Add to Todo$/i }).last();
  const botName = readE2EEnv().botName;
  const botItemPattern = botName ? new RegExp(escapeRegExp(botName), 'i') : /productivity_bot/i;
  const botItem = page.getByRole('menuitem').filter({ hasText: botItemPattern }).last();

  for (let attempt = 0; attempt < 3; attempt += 1) {
    await appsItem.hover();
    await page.waitForTimeout(600);
    if ((await isVisible(addToTodoItem)) || (await isVisible(botItem))) {
      break;
    }

    await appsItem.click({ force: true });
    await page.waitForTimeout(800);
    if ((await isVisible(addToTodoItem)) || (await isVisible(botItem))) {
      break;
    }
  }

  if (!(await isVisible(addToTodoItem))) {
    await expect(botItem).toBeVisible({ timeout: 10_000 });
    await botItem.hover();
    await botItem.click();
    await page.waitForTimeout(800);
    addToTodoItem = page.getByRole('menuitem').filter({ hasText: /^Add to Todo$/i }).last();
  }

  await expect(addToTodoItem).toBeVisible({ timeout: 10_000 });
  await addToTodoItem.click();
}

function itemActionButton(message: Locator, emojiText: string): Locator {
  return accessoryRoot(message)
    .getByRole('button', { name: emojiText, exact: true })
    .or(accessoryRoot(message).locator(`button:has(img.emoji[alt="${cssString(emojiText)}"])`))
    .first();
}

function itemCardActionButton(message: Locator, index: number): Locator {
  return accessoryRoot(message).locator('button').nth(index);
}

function accessoryRoot(message: Locator): Locator {
  return message.locator('[id^="message-accessories-"]');
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

async function locatorContainsText(locator: Locator, text: string): Promise<boolean> {
  try {
    return (await locator.innerText({ timeout: 1_000 })).includes(text);
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
