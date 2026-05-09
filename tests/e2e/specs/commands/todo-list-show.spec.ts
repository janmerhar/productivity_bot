import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  ensureAuthStateExists,
  expectDiscordModal,
  expectExecutedSlashCommand,
  expectInteractionLog,
  expectLatestChannelMessageContaining,
  expectNoDiscordInteractionFailure,
  getLogCursor,
  latestChannelMessage,
  openDiscordTestChannel,
  readE2EEnv,
  runMarker,
  runSlashCommand,
  runSlashCommandExpectingModal
} from '../../support/discord.helpers';

test.describe.configure({ mode: 'serial' });
test.setTimeout(180_000);

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

test.describe('/todo list show', () => {
  test('paginates from start to end and back with no input arguments', async ({ page }) => {
    const env = readE2EEnv();
    const setupPrefix = runMarker('e2e todo list show page');

    await clearCurrentTodoList(page);

    for (let index = 1; index <= 6; index += 1) {
      await runSlashCommand(page, `/todo add ${setupPrefix} ${index}`);
      await expectNoDiscordInteractionFailure(page);
      await expectLatestChannelMessageContaining(
        page,
        env.channelId,
        `${setupPrefix} ${index}`
      );
    }

    const listLogCursor = getLogCursor(env);

    await runSlashCommand(page, '/todo list show');
    await expectNoDiscordInteractionFailure(page);

    const listMessage = latestChannelMessage(page, env.channelId);
    await expect(listMessage).toBeVisible({ timeout: 20_000 });
    await expectExecutedSlashCommand(listMessage, /todo\s+list\s+show/i);
    await expect(listMessage).toContainText(/Page\s+1\/\d+/);
    await expectInteractionLog('todo list show', listLogCursor);

    let currentPage = await expectListPage(listMessage, 1);
    expect(currentPage.total).toBeGreaterThan(1);
    await expectNavigationState(listMessage, { previousDisabled: true });

    while (currentPage.page < currentPage.total) {
      currentPage = await moveListPage(page, listMessage, 'next', currentPage);
    }

    await expectNavigationState(listMessage, { nextDisabled: true });

    while (currentPage.page > 1) {
      currentPage = await moveListPage(page, listMessage, 'previous', currentPage);
    }

    await expectNavigationState(listMessage, { previousDisabled: true });
  });
});

type ListPage = {
  page: number;
  total: number;
};

async function expectListPage(
  message: Locator,
  expectedPage: number,
  timeout = 10_000
): Promise<ListPage> {
  await expect(message).toContainText(new RegExp(`Page\\s+${expectedPage}/\\d+`), {
    timeout
  });
  return readListPage(message);
}

async function readListPage(message: Locator): Promise<ListPage> {
  const text = await message.innerText({ timeout: 10_000 });
  const match = text.match(/Page\s+(\d+)\/(\d+)/);
  if (!match) {
    throw new Error(`Could not find list pagination footer in message text: ${text}`);
  }
  return {
    page: Number(match[1]),
    total: Number(match[2])
  };
}

async function clearCurrentTodoList(page: Page): Promise<void> {
  await runSlashCommandExpectingModal(page, '/todo list clear');
  await expectDiscordModal(page, /Clear Todo List/i);

  const dialog = page.getByRole('dialog').filter({ hasText: /Clear Todo List/i }).last();
  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expectNoDiscordInteractionFailure(page);
}

async function moveListPage(
  page: Page,
  message: Locator,
  direction: 'next' | 'previous',
  currentPage: ListPage
): Promise<ListPage> {
  const targetPage = direction === 'next' ? currentPage.page + 1 : currentPage.page - 1;

  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const button = listPaginationButton(message, direction);
    await expect(button).toBeEnabled({ timeout: 10_000 });
    await button.click();

    try {
      return await expectListPage(message, targetPage, 7_500);
    } catch (error) {
      await page.keyboard.press('Enter');
      try {
        return await expectListPage(message, targetPage, 7_500);
      } catch {
        if (attempt === 3) {
          throw error;
        }
      }
      if (attempt === 3) {
        throw error;
      }
      await page.waitForTimeout(1_000);
    }
  }

  throw new Error(`Could not move ${direction} to page ${targetPage}.`);
}

async function expectNavigationState(
  message: Locator,
  expected: { previousDisabled?: boolean; nextDisabled?: boolean }
): Promise<void> {
  if (expected.previousDisabled !== undefined) {
    const previous = listPaginationButton(message, 'previous');
    if (expected.previousDisabled) {
      await expect(previous).toBeDisabled({ timeout: 10_000 });
    } else {
      await expect(previous).toBeEnabled({ timeout: 10_000 });
    }
  }

  if (expected.nextDisabled !== undefined) {
    const next = listPaginationButton(message, 'next');
    if (expected.nextDisabled) {
      await expect(next).toBeDisabled({ timeout: 10_000 });
    } else {
      await expect(next).toBeEnabled({ timeout: 10_000 });
    }
  }
}

function listPaginationButton(message: Locator, direction: 'next' | 'previous'): Locator {
  const label = direction === 'next' ? /\u25b6|Next/i : /\u25c0|Previous/i;
  return message.getByRole('button', { name: label }).first();
}
