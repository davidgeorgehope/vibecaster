import chalk from 'chalk';
import { VibecasterClient, ApiError } from '../client.js';
import { handleApiError, displayJobResult } from '../util.js';

export function registerGenerate(program) {
  program
    .command('generate <url>')
    .description('Generate posts from a URL (preview only)')
    .action(async (url) => {
      const client = new VibecasterClient();

      console.log(chalk.cyan.bold('\n  Generating from URL'));
      console.log(`  ${url}\n`);

      let job;
      try {
        job = await client.submitAndPoll('/cli/generate-from-url', {
          url,
          platforms: [],
        });
      } catch (e) {
        if (e instanceof ApiError) handleApiError(e);
        throw e;
      }

      if (job.status === 'complete') {
        displayJobResult(job);
      } else if (job.status === 'failed') {
        console.log(chalk.red(`  Failed: ${job.error || 'Unknown'}`));
      }
    });
}
