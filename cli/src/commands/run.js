import chalk from 'chalk';
import { VibecasterClient, ApiError } from '../client.js';
import { handleApiError } from '../util.js';

export function registerRun(program) {
  program
    .command('run')
    .description('Trigger a campaign run immediately')
    .action(async () => {
      const client = new VibecasterClient();

      console.log('Triggering campaign run...');
      try {
        await client.post('/run-now');
      } catch (e) {
        if (e instanceof ApiError) handleApiError(e);
        throw e;
      }

      console.log(chalk.green('Campaign run started! Check connected platforms for new posts.'));
    });
}
