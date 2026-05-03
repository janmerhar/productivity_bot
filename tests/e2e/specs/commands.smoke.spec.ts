import { test } from '@playwright/test';
import {
  ensureAuthStateExists,
  expectBotActivity,
  expectInteractionLog,
  expectNoDiscordInteractionFailure,
  getLogCursor,
  openDiscordTestChannel,
  readE2EEnv,
  runMarker,
  runSlashCommand
} from '../support/discord.helpers';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  ensureAuthStateExists();
  readE2EEnv();
});

test.beforeEach(async ({ page }) => {
  await openDiscordTestChannel(page, readE2EEnv());
});

const readOnlyCommands = [
  { name: 'info', input: '/info' },
  { name: 'todo overview', input: '/todo overview' },
  { name: 'list directory', input: '/list directory' },
  { name: 'reminder list', input: '/reminder list' },
  { name: 'habit list', input: '/habit list' },
  { name: 'pomodoro active', input: '/pomodoro active' }
];

for (const command of readOnlyCommands) {
  test(`${command.name} executes from Discord Web`, async ({ page }) => {
    const env = readE2EEnv();
    const logCursor = getLogCursor(env);

    await runSlashCommand(page, command.input);

    await expectNoDiscordInteractionFailure(page);
    await expectBotActivity(page, env);
    await expectInteractionLog(command.name, logCursor);
  });
}

test.describe('mutating smoke flows', () => {
  test.skip(
    process.env.DISCORD_E2E_MUTATING !== 'true',
    'Set DISCORD_E2E_MUTATING=true to run tests that create bot data.'
  );

  test('todo add executes from Discord Web', async ({ page }) => {
    const env = readE2EEnv();
    const logCursor = getLogCursor(env);
    const todo = runMarker('e2e todo');

    await runSlashCommand(page, `/todo add todo:${todo}`);

    await expectNoDiscordInteractionFailure(page);
    await expectBotActivity(page, env);
    await expectInteractionLog('todo add', logCursor);
  });

  test('habit add executes from Discord Web', async ({ page }) => {
    const env = readE2EEnv();
    const logCursor = getLogCursor(env);
    const habit = runMarker('e2e habit');

    await runSlashCommand(page, `/habit add habit:${habit}`);

    await expectNoDiscordInteractionFailure(page);
    await expectBotActivity(page, env);
    await expectInteractionLog('habit add', logCursor);
  });

  test('pomodoro start and stop execute from Discord Web', async ({ page }) => {
    const env = readE2EEnv();
    const startCursor = getLogCursor(env);

    await runSlashCommand(page, '/pomodoro start duration:1 autojoin:Off');
    await expectNoDiscordInteractionFailure(page);
    await expectBotActivity(page, env);
    await expectInteractionLog('pomodoro start', startCursor);

    const stopCursor = getLogCursor(env);
    await runSlashCommand(page, '/pomodoro stop');
    await expectNoDiscordInteractionFailure(page);
    await expectBotActivity(page, env);
    await expectInteractionLog('pomodoro stop', stopCursor);
  });
});
