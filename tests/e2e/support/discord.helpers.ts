import fs from 'node:fs';
import path from 'node:path';
import { expect, type Locator, type Page } from '@playwright/test';

export type E2EEnv = {
  guildId: string;
  channelId: string;
  botName?: string;
  assertLog: boolean;
  logFile: string;
};

export type LogCursor = {
  filePath: string;
  size: number;
};

const failureText = /application did not respond|interaction failed|something went wrong/i;
const e2eRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(e2eRoot, '..', '..');

export function readE2EEnv(): E2EEnv {
  const guildId = process.env.DISCORD_E2E_GUILD_ID;
  const channelId = process.env.DISCORD_E2E_CHANNEL_ID;

  if (!guildId || !channelId) {
    throw new Error(
      [
        'Missing Discord E2E environment.',
        'Set DISCORD_E2E_GUILD_ID and DISCORD_E2E_CHANNEL_ID before running npm.cmd --prefix tests/e2e run e2e.',
        'The channel should be in a dedicated test guild where the bot is installed.'
      ].join(' ')
    );
  }

  return {
    guildId,
    channelId,
    botName: process.env.DISCORD_E2E_BOT_NAME,
    assertLog: process.env.DISCORD_E2E_ASSERT_LOG === 'true',
    logFile: process.env.DISCORD_E2E_LOG_FILE || process.env.APP_LOG_FILE || 'discord.log'
  };
}

export function ensureAuthStateExists(): void {
  const authFile = path.resolve(e2eRoot, '.auth', 'discord-user.json');
  if (!fs.existsSync(authFile)) {
    throw new Error(
      `Missing Discord auth state at ${authFile}. Run npm.cmd --prefix tests/e2e run e2e:auth first.`
    );
  }
}

export function discordChannelUrl(env: E2EEnv): string {
  return `https://discord.com/channels/${env.guildId}/${env.channelId}`;
}

export async function openDiscordTestChannel(page: Page, env: E2EEnv): Promise<void> {
  await page.goto(discordChannelUrl(env), { waitUntil: 'domcontentloaded' });
  await expect(page).toHaveURL(new RegExp(`/channels/${env.guildId}/${env.channelId}`), {
    timeout: 30_000
  });
  await getMessageBox(page);
}

export async function runSlashCommand(page: Page, commandLine: string): Promise<void> {
  const messageBox = await getMessageBox(page);
  await messageBox.click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.press('Backspace');
  await page.keyboard.type(commandLine, { delay: 20 });
  await page.waitForTimeout(500);

  // First Enter selects the slash command from Discord's command picker.
  await page.keyboard.press('Enter');

  // Discord Web can take a moment to move from the picker into the command composer.
  // Refocus the composer before pressing Enter so the command is submitted, not just selected.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.waitForTimeout(750);
    const commandComposer = await getMessageBox(page);
    await commandComposer.click();
    await commandComposer.press('Enter');
  }
}

export async function runSlashCommandExpectingModal(
  page: Page,
  commandLine: string
): Promise<void> {
  const messageBox = await getMessageBox(page);
  await messageBox.click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.press('Backspace');
  await page.keyboard.type(commandLine, { delay: 20 });
  await page.waitForTimeout(500);

  await page.keyboard.press('Enter');
  await page.waitForTimeout(750);

  const commandComposer = await getMessageBox(page);
  await commandComposer.click();
  await commandComposer.press('Enter');
}

export type SlashCommandOptionInput = {
  name: string;
  value: string;
};

export type SlashCommandAutocompleteSelection = {
  query: string;
  selectionText?: string | RegExp;
};

export type SlashCommandAutocompleteOptionInput = {
  name: string;
  query: string;
  selectionText?: string | RegExp;
};

export async function runSlashCommandWithOptions(
  page: Page,
  commandLine: string,
  options: SlashCommandOptionInput[]
): Promise<void> {
  const messageBox = await getMessageBox(page);
  await messageBox.click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.press('Backspace');
  await page.keyboard.type(commandLine, { delay: 20 });
  await waitForSlashCommandComposer(page);
  await page.waitForTimeout(500);

  for (const option of options) {
    await openSlashCommandOptionsMenu(page);
    await page.keyboard.type(option.name, { delay: 20 });
    await page.waitForTimeout(300);
    await page.keyboard.press('Enter');
    await expect(
      page
        .locator('[class*="optionPillKey"]')
        .filter({ hasText: new RegExp(escapeRegExp(option.name), 'i') })
        .last()
    ).toBeVisible({ timeout: 5_000 });
    await page.keyboard.type(option.value, { delay: 20 });
    await page.waitForTimeout(300);
  }

  const commandComposer = await getMessageBox(page);
  await commandComposer.click();
  await commandComposer.press('Enter');
}

export async function runSlashCommandWithAutocompleteOptions(
  page: Page,
  commandLine: string,
  options: SlashCommandAutocompleteOptionInput[]
): Promise<void> {
  const messageBox = await getMessageBox(page);
  await messageBox.click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.press('Backspace');
  await page.keyboard.type(commandLine, { delay: 20 });
  await waitForSlashCommandComposer(page);
  await page.waitForTimeout(500);

  for (const option of options) {
    await openSlashCommandOptionsMenu(page);
    await page.keyboard.type(option.name, { delay: 20 });
    await page.waitForTimeout(300);
    await page.keyboard.press('Enter');
    await expect(
      page
        .locator('[class*="optionPillKey"]')
        .filter({ hasText: new RegExp(escapeRegExp(option.name), 'i') })
        .last()
    ).toBeVisible({ timeout: 5_000 });

    await page.keyboard.type(option.query, { delay: 20 });
    await page.waitForTimeout(300);

    const selectionText = option.selectionText ?? option.query;
    const selectionPattern =
      typeof selectionText === 'string'
        ? new RegExp(escapeRegExp(selectionText), 'i')
        : selectionText;
    const selection = page.getByRole('option').filter({ hasText: selectionPattern }).first();
    await expect(selection).toBeVisible({ timeout: 10_000 });
    await selection.click();
    await page.waitForTimeout(300);
  }

  const commandComposer = await getMessageBox(page);
  await commandComposer.click();
  await commandComposer.press('Enter');
}

export async function runSlashCommandWithAutocompleteSelection(
  page: Page,
  commandLine: string,
  query: string,
  selectionText: string | RegExp = query
): Promise<void> {
  await runSlashCommandWithAutocompleteSelections(page, commandLine, [
    { query, selectionText }
  ]);
}

export async function runSlashCommandWithAutocompleteSelections(
  page: Page,
  commandLine: string,
  selections: SlashCommandAutocompleteSelection[]
): Promise<void> {
  await runSlashCommandWithAutocompleteSelectionsAndText(page, commandLine, selections, '');
}

export async function runSlashCommandWithAutocompleteSelectionsAndText(
  page: Page,
  commandLine: string,
  selections: SlashCommandAutocompleteSelection[],
  textAfterSelections: string
): Promise<void> {
  const messageBox = await getMessageBox(page);
  await messageBox.click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.press('Backspace');
  await page.keyboard.type(commandLine, { delay: 20 });
  await waitForSlashCommandComposer(page);
  await page.waitForTimeout(500);

  for (const selectionInput of selections) {
    const query = selectionInput.query;
    const selectionText = selectionInput.selectionText ?? query;
    await page.keyboard.type(query, { delay: 20 });

    const selectionPattern =
      typeof selectionText === 'string'
        ? new RegExp(escapeRegExp(selectionText), 'i')
        : selectionText;
    const selection = page.getByRole('option').filter({ hasText: selectionPattern }).first();
    await expect(selection).toBeVisible({ timeout: 10_000 });
    await selection.click();
    await page.waitForTimeout(300);
  }

  if (textAfterSelections) {
    await page.keyboard.type(textAfterSelections, { delay: 20 });
    await page.waitForTimeout(300);
  }

  const commandComposer = await getMessageBox(page);
  await commandComposer.click();
  await commandComposer.press('Enter');
}

export async function expectNoDiscordInteractionFailure(page: Page): Promise<void> {
  await page.waitForTimeout(3_500);
  await expect(page.getByText(failureText)).toHaveCount(0);
}

export async function expectBotActivity(page: Page, env: E2EEnv): Promise<void> {
  const deadline = Date.now() + 20_000;
  const responseIndicators = [
    page.getByText(/only you can see this/i).last(),
    page.getByText(/dismiss message/i).last()
  ];

  if (env.botName) {
    responseIndicators.push(page.getByText(env.botName).last());
  }

  while (Date.now() < deadline) {
    for (const indicator of responseIndicators) {
      if (await isVisible(indicator)) {
        return;
      }
    }
    await page.waitForTimeout(500);
  }

  throw new Error(
    env.botName
      ? `Did not find a Discord response indicator or bot name "${env.botName}".`
      : 'Did not find a Discord response indicator.'
  );
}

export function latestChannelMessage(page: Page, channelId: string): Locator {
  return page.locator(`li[id^="chat-messages-${channelId}-"]`).last();
}

export async function expectLatestChannelMessageContaining(
  page: Page,
  channelId: string,
  text: string | RegExp
): Promise<Locator> {
  const message = latestChannelMessage(page, channelId);
  await expect(message).toBeVisible({ timeout: 20_000 });
  await expect(message).toContainText(text, { timeout: 20_000 });
  return message;
}

export async function expectExecutedSlashCommand(
  message: Locator,
  commandName: string | RegExp
): Promise<void> {
  const commandText =
    typeof commandName === 'string'
      ? new RegExp(escapeRegExp(commandName).replace(/\s+/g, '\\s+'), 'i')
      : commandName;
  const executedCommand = message
    .locator('div[class*="executedCommand"]')
    .filter({ hasText: commandText })
    .first();

  await expect(executedCommand).toBeVisible({ timeout: 10_000 });
  await expect(executedCommand).toContainText(commandText);
}

export async function expectDiscordModal(
  page: Page,
  title: string | RegExp
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: title }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });
}

export async function dismissDiscordModal(page: Page): Promise<void> {
  const dialog = page.getByRole('dialog').last();
  if (!(await isVisible(dialog))) {
    return;
  }

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden({ timeout: 5_000 });
}

export async function submitDiscordModal(
  page: Page,
  title: string | RegExp,
  value: string
): Promise<void> {
  const dialog = page.getByRole('dialog').filter({ hasText: title }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  const input = dialog.getByRole('textbox').first();
  await expect(input).toBeVisible({ timeout: 5_000 });
  await input.fill(value);

  await dialog.getByRole('button', { name: /submit/i }).click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
}

export function getLogCursor(env: E2EEnv): LogCursor | null {
  if (!env.assertLog) {
    return null;
  }

  const filePath = path.isAbsolute(env.logFile)
    ? env.logFile
    : path.resolve(repoRoot, env.logFile);
  return {
    filePath,
    size: fs.existsSync(filePath) ? fs.statSync(filePath).size : 0
  };
}

export async function expectInteractionLog(
  commandName: string,
  cursor: LogCursor | null
): Promise<void> {
  if (!cursor) {
    return;
  }

  const deadline = Date.now() + 20_000;
  const expected = `command=${commandName}`;

  while (Date.now() < deadline) {
    if (fs.existsSync(cursor.filePath)) {
      const text = fs.readFileSync(cursor.filePath, 'utf8').slice(cursor.size);
      if (text.includes(expected)) {
        return;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  throw new Error(`Did not find "${expected}" in ${cursor.filePath}`);
}

export function runMarker(prefix: string): string {
  return `${prefix} ${new Date().toISOString()}`;
}

async function getMessageBox(page: Page): Promise<Locator> {
  const candidates = [
    page.locator('[role="textbox"][data-slate-editor="true"]').last(),
    page.getByRole('textbox', { name: /message/i }).last(),
    page.locator('[aria-label^="Message"]').last()
  ];

  for (const candidate of candidates) {
    if (await isVisible(candidate)) {
      return candidate;
    }
  }

  const fallback = page.locator('[role="textbox"]').last();
  await expect(fallback).toBeVisible({ timeout: 30_000 });
  return fallback;
}

async function isVisible(locator: Locator): Promise<boolean> {
  try {
    return await locator.isVisible({ timeout: 1_000 });
  } catch {
    return false;
  }
}

async function openSlashCommandOptionsMenu(page: Page): Promise<void> {
  const clickPoint = await page.evaluate(() => {
    const editor = document.querySelector('[data-slate-editor="true"]');
    const pills = Array.from(document.querySelectorAll('[class*="optionPill"]'));
    const lastPill = pills[pills.length - 1];
    if (!(editor instanceof HTMLElement) || !(lastPill instanceof HTMLElement)) {
      throw new Error('Could not find the Discord slash command option area.');
    }

    const editorRect = editor.getBoundingClientRect();
    const pillRect = lastPill.getBoundingClientRect();
    return {
      x: Math.min(pillRect.right + 25, editorRect.right - 10),
      y: pillRect.y + pillRect.height / 2
    };
  });

  await page.mouse.click(clickPoint.x, clickPoint.y);
  await expect(page.locator('[aria-expanded="true"][data-slate-editor="true"]')).toBeVisible({
    timeout: 5_000
  });
}

async function waitForSlashCommandComposer(page: Page): Promise<void> {
  const commandComposer = page.locator('[class*="applicationCommand"]').last();
  try {
    await commandComposer.waitFor({ state: 'visible', timeout: 2_000 });
    return;
  } catch {
    // Discord sometimes leaves the typed slash command as plain text until Enter
    // selects it from the command picker.
    await page.keyboard.press('Enter');
  }

  await expect(commandComposer).toBeVisible({ timeout: 10_000 });
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
