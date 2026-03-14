import chalk from 'chalk';
import { loadConfig, saveConfig } from '../config.js';
import readline from 'readline';

function prompt(question, defaultValue = '') {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const suffix = defaultValue ? ` (${defaultValue})` : '';
  return new Promise((resolve) => {
    rl.question(`${question}${suffix}: `, (answer) => {
      rl.close();
      resolve(answer || defaultValue);
    });
  });
}

function promptHidden(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    // Use raw mode to hide input
    if (process.stdin.isTTY) {
      process.stdout.write(`${question}: `);
      process.stdin.setRawMode(true);
      process.stdin.resume();
      let input = '';
      const onData = (ch) => {
        const c = ch.toString();
        if (c === '\n' || c === '\r') {
          process.stdin.setRawMode(false);
          process.stdin.pause();
          process.stdin.removeListener('data', onData);
          process.stdout.write('\n');
          rl.close();
          resolve(input);
        } else if (c === '\u0003') {
          // Ctrl+C
          process.exit(0);
        } else if (c === '\u007f' || c === '\b') {
          input = input.slice(0, -1);
        } else {
          input += c;
        }
      };
      process.stdin.on('data', onData);
    } else {
      rl.question(`${question}: `, (answer) => {
        rl.close();
        resolve(answer);
      });
    }
  });
}

export function registerLogin(program) {
  program
    .command('login')
    .description('Configure API credentials')
    .option('--api-url <url>', 'Vibecaster API base URL')
    .option('--api-key <key>', 'Your Vibecaster API key (vb_...)')
    .action(async (options) => {
      const apiUrl = (options.apiUrl || await prompt('API URL', 'https://vibecaster.ai/api')).replace(/\/+$/, '');
      const apiKey = options.apiKey || await promptHidden('API Key');

      if (!apiKey) {
        console.error(chalk.red('Error: API key is required'));
        process.exit(1);
      }

      if (!apiKey.startsWith('vb_')) {
        console.log(chalk.yellow("Warning: API key should start with 'vb_'"));
      }

      console.log('Testing connection...');
      try {
        const response = await fetch(`${apiUrl}/auth/status`, {
          headers: { 'X-API-Key': apiKey },
          signal: AbortSignal.timeout(10000),
        });
        if (response.status === 401) {
          console.error(chalk.red('Error: Invalid API key'));
          process.exit(1);
        } else if (response.status >= 400) {
          console.error(chalk.red(`Error: API returned ${response.status}`));
          process.exit(1);
        }
      } catch (err) {
        if (err.name === 'TimeoutError') {
          console.error(chalk.red(`Error: Connection to ${apiUrl} timed out`));
        } else {
          console.error(chalk.red(`Error: Could not connect to ${apiUrl}`));
        }
        process.exit(1);
      }

      const config = loadConfig();
      config.api_url = apiUrl;
      config.api_key = apiKey;
      saveConfig(config);

      console.log(chalk.green('Logged in successfully!'));
      console.log('Config saved to ~/.vibecaster/config.json');
    });
}
