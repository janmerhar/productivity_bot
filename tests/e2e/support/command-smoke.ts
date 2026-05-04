import { type Page } from '@playwright/test';
import {
  dismissDiscordModal,
  expectBotActivity,
  expectDiscordModal,
  expectInteractionLog,
  expectNoDiscordInteractionFailure,
  getLogCursor,
  readE2EEnv,
  runSlashCommand,
  submitDiscordModal
} from './discord.helpers';

export type CommandSmokeCase = {
  name: string;
  input: string;
  expectedLog?: string;
  modalTitle?: string | RegExp;
  modalValue?: string;
  modalValueEnv?: string;
  allowBotActivityInsteadOfModal?: boolean;
};

export function envFlagEnabled(name: string): boolean {
  return process.env[name] === 'true';
}

export async function runCommandSmoke(
  page: Page,
  command: CommandSmokeCase
): Promise<void> {
  const env = readE2EEnv();
  const logCursor = getLogCursor(env);
  const modalValue = readModalValue(command);

  await runSlashCommand(page, command.input);
  await expectNoDiscordInteractionFailure(page);

  if (command.modalTitle) {
    try {
      await expectDiscordModal(page, command.modalTitle);
      if (modalValue === undefined) {
        await dismissDiscordModal(page);
      } else {
        await submitDiscordModal(page, command.modalTitle, modalValue);
        await expectNoDiscordInteractionFailure(page);
        await expectBotActivity(page, env);
      }
    } catch (error) {
      if (!command.allowBotActivityInsteadOfModal) {
        throw error;
      }
      await expectBotActivity(page, env);
    }
  } else {
    await expectBotActivity(page, env);
  }

  await expectInteractionLog(command.expectedLog ?? command.name, logCursor);
}

function readModalValue(command: CommandSmokeCase): string | undefined {
  if (command.modalValue !== undefined) {
    return command.modalValue;
  }
  if (!command.modalValueEnv) {
    return undefined;
  }

  const value = process.env[command.modalValueEnv]?.trim();
  if (!value) {
    throw new Error(
      `Missing ${command.modalValueEnv}. Set it in tests/e2e/.env before running ${command.name}.`
    );
  }
  return value;
}
