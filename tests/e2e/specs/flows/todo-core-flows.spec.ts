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
  runSlashCommandExpectingModal,
  runSlashCommandWithAutocompleteOptions
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });
test.setTimeout(240_000);

const emoji = {
  add: '\u2795',
  complete: '\u2705',
  duplicate: '\ud83d\udcc4',
  edit: '\u270f\ufe0f',
  listShow: '\ud83d\udccb',
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

test.describe('todo flows', () => {
  test('create, duplicate, edit, and complete', async ({ page }) => {
    const env = readE2EEnv();
    const title = runMarker('e2e flow duplicate');
    const editedTitle = runMarker('e2e flow duplicate edited');
    const editedDescription = runMarker('e2e flow duplicate description');

    await runSlashCommand(page, `/todo add ${title}`);
    await expectNoDiscordInteractionFailure(page);

    const originalCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await itemActionButton(originalCard, emoji.duplicate).click();
    await expectNoDiscordInteractionFailure(page);

    const duplicatedCard = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      /Duplicated todo\./i
    );
    await expect(duplicatedCard).toContainText(title);

    await itemActionButton(duplicatedCard, emoji.edit).click();
    await fillTodoModal(page, {
      title: editedTitle,
      description: editedDescription,
      modalTitle: /Edit/i
    });

    await expect(duplicatedCard).toContainText(editedTitle, { timeout: 20_000 });
    await expect(duplicatedCard).toContainText(editedDescription);

    await itemActionButton(duplicatedCard, emoji.progress).click();
    await expect(duplicatedCard).toContainText(/Status\s*In Progress/, {
      timeout: 20_000
    });

    await itemActionButton(duplicatedCard, emoji.complete).click();
    await expect(duplicatedCard).toContainText(/Status\s*Done/, { timeout: 20_000 });
    await expect(itemActionButton(duplicatedCard, emoji.complete)).toBeDisabled({
      timeout: 10_000
    });
  });

  test('create from list view', async ({ page }) => {
    const env = readE2EEnv();
    const title = runMarker('e2e flow list add');
    const description = runMarker('e2e flow list add description');

    await clearCurrentTodoList(page);

    await runSlashCommand(page, '/todo list show');
    await expectNoDiscordInteractionFailure(page);

    const listMessage = latestChannelMessage(page, env.channelId);
    await expect(listMessage).toContainText(/Tasks/i, { timeout: 20_000 });

    await itemActionButton(listMessage, emoji.add).click();
    await fillTodoModal(page, {
      title,
      description,
      modalTitle: /Add to/i
    });

    await expect(listMessage).toContainText(title, { timeout: 20_000 });
    await clickEntryNumberButton(listMessage, title);

    const detailsCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expect(detailsCard).toContainText(description);

    await completeItemFromCard(detailsCard);
  });

  test('list options search and status filter', async ({ page }) => {
    const env = readE2EEnv();
    const marker = Date.now().toString(36);
    const todoTitle = `todo-${marker}`;
    const inProgressTitle = `progress-${marker}`;
    const doneTitle = `done-${marker}`;

    await clearCurrentTodoList(page);

    await runSlashCommand(page, `/todo add ${todoTitle}`);
    await expectNoDiscordInteractionFailure(page);
    await expectLatestChannelMessageContaining(page, env.channelId, todoTitle);

    await runSlashCommand(page, `/todo add ${inProgressTitle}`);
    await expectNoDiscordInteractionFailure(page);
    const inProgressCard = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      inProgressTitle
    );
    await itemActionButton(inProgressCard, emoji.progress).click();
    await expect(inProgressCard).toContainText(/Status\s*In Progress/, {
      timeout: 20_000
    });

    await runSlashCommand(page, `/todo add ${doneTitle}`);
    await expectNoDiscordInteractionFailure(page);
    const doneCard = await expectLatestChannelMessageContaining(page, env.channelId, doneTitle);
    await completeItemFromCard(doneCard);

    await runSlashCommand(page, '/todo list show');
    await expectNoDiscordInteractionFailure(page);

    const listMessage = latestChannelMessage(page, env.channelId);
    await expect(listMessage).toContainText(todoTitle, { timeout: 20_000 });
    await itemActionButton(listMessage, emoji.options).click();
    await fillListOptionsModal(page, { status: 'Done', search: doneTitle });

    await expect(listMessage).toContainText(doneTitle, { timeout: 20_000 });
    await expect(listMessage).not.toContainText(todoTitle);
    await expect(listMessage).not.toContainText(inProgressTitle);
    await expect(listMessage).toContainText(/Status:\s*Done/i);
    await expect(listMessage).toContainText(new RegExp(`Search:\\s*${escapeRegExp(doneTitle)}`));

    await itemActionButton(listMessage, emoji.options).click();
    await fillListOptionsModal(page, { status: 'All', search: '' });
    await expect(listMessage).toContainText(/Status:\s*All/i, { timeout: 20_000 });
    await expect(listMessage).toContainText(/Search:\s*All/i);
  });

  test('create new list during todo add', async ({ page }) => {
    const env = readE2EEnv();
    const title = runMarker('e2e flow add creates list item');
    const listName = runMarker('zzzz e2e flow add creates list');

    await runSlashCommandWithAutocompleteOptions(page, `/todo add ${title}`, [
      {
        name: 'list',
        query: 'Create new list',
        selectionText: /Create new list/i
      }
    ]);
    await expectDiscordModal(page, /Create New List/i);
    await fillSingleFieldModal(page, /Create New List/i, listName);

    const createdCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expect(createdCard).toContainText(listName);

    await runSlashCommand(page, '/todo list directory');
    await expectNoDiscordInteractionFailure(page);

    const directoryMessage = latestChannelMessage(page, env.channelId);
    await sortDirectoryDescending(directoryMessage);
    await expect(directoryMessage).toContainText(listName, { timeout: 20_000 });
    await expect(directoryMessage).toContainText(new RegExp(`${escapeRegExp(listName)}[\\s\\S]*Items:\\s*1`));
  });

  test('directory to list to item', async ({ page }) => {
    const env = readE2EEnv();
    const listName = runMarker('e2e flow directory list');
    const title = runMarker('e2e flow directory item');
    const description = runMarker('e2e flow directory description');

    await runSlashCommand(page, '/todo list directory');
    await expectNoDiscordInteractionFailure(page);

    const directoryMessage = latestChannelMessage(page, env.channelId);
    await itemActionButton(directoryMessage, emoji.add).click();
    await fillSingleFieldModal(page, /Create New List/i, listName);

    await expect(directoryMessage).toContainText(listName, { timeout: 20_000 });
    await clickEntryNumberButton(directoryMessage, listName);

    const listCard = await expectLatestChannelMessageContaining(page, env.channelId, listName);
    await expect(listCard).toContainText(/Todo List/i);

    await itemActionButton(listCard, emoji.add).click();
    await fillTodoModal(page, {
      title,
      description,
      modalTitle: /Add to/i
    });

    await itemActionButton(listCard, emoji.listShow).click();
    const listItemsMessage = await expectLatestChannelMessageContaining(
      page,
      env.channelId,
      title
    );
    await expect(listItemsMessage).toContainText(description);
  });

  test('move item between lists by editing', async ({ page }) => {
    const env = readE2EEnv();
    const listA = runMarker('e2e flow move list a');
    const listB = runMarker('e2e flow move list b');
    const title = runMarker('e2e flow moved item');

    await createTodoList(page, listA);
    await createTodoList(page, listB);

    await runSlashCommandWithAutocompleteOptions(page, `/todo add ${title}`, [
      { name: 'list', query: listA, selectionText: listA }
    ]);
    await expectNoDiscordInteractionFailure(page);

    const itemCard = await expectLatestChannelMessageContaining(page, env.channelId, title);
    await expect(itemCard).toContainText(listA);

    await itemActionButton(itemCard, emoji.edit).click();
    await setEditModalList(page, listB);

    await expect(itemCard).toContainText(listB, { timeout: 20_000 });
    await expect(itemCard).toContainText(title);

    await showTodoList(page, listA);
    const listAMessage = latestChannelMessage(page, env.channelId);
    await expect(listAMessage).toContainText(/Tasks/i, { timeout: 20_000 });
    await expect(listAMessage).not.toContainText(title);

    await showTodoList(page, listB);
    const listBMessage = latestChannelMessage(page, env.channelId);
    await expect(listBMessage).toContainText(title, { timeout: 20_000 });
  });
});

async function createTodoList(page: Page, listName: string): Promise<void> {
  const env = readE2EEnv();
  await runSlashCommand(page, `/todo list create ${listName}`);
  await expectNoDiscordInteractionFailure(page);
  await expectLatestChannelMessageContaining(page, env.channelId, listName);
}

async function showTodoList(page: Page, listName: string): Promise<void> {
  await runSlashCommandWithAutocompleteOptions(page, '/todo list show', [
    { name: 'list', query: listName, selectionText: listName }
  ]);
  await expectNoDiscordInteractionFailure(page);
}

async function clearCurrentTodoList(page: Page): Promise<void> {
  await runSlashCommandExpectingModal(page, '/todo list clear');
  await expectDiscordModal(page, /Clear Todo List/i);

  const dialog = page.getByRole('dialog').filter({ hasText: /Clear Todo List/i }).last();
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function fillTodoModal(
  page: Page,
  input: { title: string; description?: string; modalTitle: string | RegExp }
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: input.modalTitle }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  await dialog.getByRole('textbox').nth(0).fill(input.title);
  if (input.description !== undefined) {
    await dialog.getByRole('textbox').nth(1).fill(input.description);
  }

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

async function fillListOptionsModal(
  page: Page,
  options: { status: 'All' | 'Done'; search: string }
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: /View Options/i }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  await clickModalRadio(dialog, options.status);
  await dialog.getByRole('textbox').first().fill(options.search);
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function setEditModalList(page: Page, listName: string): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: /Edit/i }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  const namedListTextbox = dialog.getByRole('textbox', { name: /^List$/i }).last();
  if (await isVisible(namedListTextbox)) {
    await namedListTextbox.fill(listName);
  } else {
    const textboxes = dialog.getByRole('textbox');
    if ((await textboxes.count()) >= 5) {
      await textboxes.last().fill(listName);
    } else {
      const select = dialog.getByRole('combobox').last();
      await expect(select).toBeVisible({ timeout: 5_000 });
      await select.click();
      const option = page
        .getByRole('option')
        .filter({ hasText: new RegExp(escapeRegExp(listName), 'i') })
        .first();
      await expect(option).toBeVisible({ timeout: 10_000 });
      await option.click();
    }
  }

  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function clickModalRadio(dialog: Locator, label: string): Promise<void> {
  const radio = dialog.getByRole('radio', {
    name: new RegExp(`^${escapeRegExp(label)}$`, 'i')
  });
  if (await isVisible(radio)) {
    await radio.click();
    return;
  }

  await dialog.getByText(new RegExp(`^${escapeRegExp(label)}$`, 'i')).first().click();
}

async function completeItemFromCard(card: Locator): Promise<void> {
  await itemActionButton(card, emoji.progress).click();
  await expect(card).toContainText(/Status\s*In Progress/, { timeout: 20_000 });
  await itemActionButton(card, emoji.complete).click();
  await expect(card).toContainText(/Status\s*Done/, { timeout: 20_000 });
  await expect(itemActionButton(card, emoji.complete)).toBeDisabled({ timeout: 10_000 });
}

async function clickEntryNumberButton(message: Locator, entryText: string): Promise<void> {
  const text = await message.innerText({ timeout: 10_000 });
  const entryLine = text
    .split(/\r?\n/)
    .find((line) => line.toLowerCase().includes(entryText.toLowerCase()));
  const number =
    entryLine?.match(/([1-5])\ufe0f?\u20e3/)?.[1] ??
    entryLine?.match(/^\s*([1-5])\s+/)?.[1];
  if (!number) {
    throw new Error(`Could not find a visible numbered entry for "${entryText}".`);
  }

  await accessoryRoot(message).getByRole('button', { name: number, exact: true }).click();
}

async function sortDirectoryDescending(directoryMessage: Locator): Promise<void> {
  const buttons = accessoryRoot(directoryMessage).getByRole('button');
  await expect(buttons.nth(7)).toBeEnabled({ timeout: 10_000 });
  await buttons.nth(7).click();
}

function itemActionButton(message: Locator, emojiText: string): Locator {
  return accessoryRoot(message)
    .locator(`button:has(img.emoji[alt="${cssString(emojiText)}"])`)
    .first();
}

function accessoryRoot(message: Locator): Locator {
  return message.locator('[id^="message-accessories-"]').first();
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
