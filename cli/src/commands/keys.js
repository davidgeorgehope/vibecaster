import chalk from 'chalk';
import readline from 'readline';
import { VibecasterClient, ApiError } from '../client.js';
import { formatTimestamp, handleApiError } from '../util.js';

export function registerKeys(program) {
  const keysCmd = program
    .command('keys')
    .description('Manage API keys')
    .action(async () => {
      // Default action: list keys
      await listKeys();
    });

  keysCmd
    .command('list')
    .description('List all API keys')
    .action(listKeys);

  keysCmd
    .command('create <name>')
    .description('Create a new API key (requires web UI login)')
    .action(async (name) => {
      const client = new VibecasterClient();

      let result;
      try {
        result = await client.post('/api-keys', { name });
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.statusCode === 403) {
            console.log(chalk.yellow('API key creation requires web UI login (JWT auth).'));
            console.log('Create keys at: https://vibecaster.ai → Dashboard → CLI');
            process.exit(1);
          }
          handleApiError(e);
        }
        throw e;
      }

      console.log(chalk.green.bold('\n  API Key Created!'));
      console.log(chalk.gray('  ' + '─'.repeat(50)));
      console.log(`\n  Name:   ${result.name}`);
      console.log(`  Prefix: ${result.key_prefix}...`);
      console.log(`\n  ${chalk.yellow('Full Key (save this now, it will not be shown again):')}`);
      console.log(`  ${chalk.green.bold(result.key || '')}`);
      console.log();
    });

  keysCmd
    .command('revoke <id>')
    .description('Revoke an API key by ID')
    .action(async (id) => {
      // Confirm
      const confirmed = await confirm('Are you sure you want to revoke this API key?');
      if (!confirmed) {
        console.log('Cancelled.');
        return;
      }

      const client = new VibecasterClient();

      try {
        await client.del(`/api-keys/${id}`);
      } catch (e) {
        if (e instanceof ApiError) handleApiError(e);
        throw e;
      }

      console.log(chalk.yellow('API key revoked.'));
    });
}

async function listKeys() {
  const client = new VibecasterClient();

  let apiKeys;
  try {
    apiKeys = await client.get('/api-keys');
  } catch (e) {
    if (e instanceof ApiError) handleApiError(e);
    throw e;
  }

  if (!apiKeys || apiKeys.length === 0) {
    console.log('No API keys found.');
    return;
  }

  console.log(chalk.cyan.bold('\n  API Keys'));
  console.log(chalk.gray('  ' + '─'.repeat(50)));

  for (const key of apiKeys) {
    const active = key.is_active;
    const statusDot = active ? chalk.green('●') : chalk.red('●');
    const name = key.name || 'Unnamed';
    const prefix = key.key_prefix || '';
    const created = formatTimestamp(key.created_at);
    const lastUsed = formatTimestamp(key.last_used_at);

    console.log(`\n  ${statusDot} ${chalk.bold(name)}  (ID: ${key.id})`);
    console.log(`    Prefix: ${prefix}...`);
    console.log(`    Created: ${created}  |  Last used: ${lastUsed}`);
    if (!active) {
      console.log(`    ${chalk.red('REVOKED')}`);
    }
  }

  console.log();
}

function confirm(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(`${question} [y/N] `, (answer) => {
      rl.close();
      resolve(answer.toLowerCase() === 'y' || answer.toLowerCase() === 'yes');
    });
  });
}
