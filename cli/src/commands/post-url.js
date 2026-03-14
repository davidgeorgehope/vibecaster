import chalk from 'chalk';
import { VibecasterClient, ApiError } from '../client.js';
import { handleApiError, displayJobResult, expandPlatforms } from '../util.js';

export function registerPostUrl(program) {
  program
    .command('post-url <url>')
    .description('Generate and post content from a URL')
    .option('-p, --platform <platform...>', 'Platform(s) to post to: twitter, linkedin, all', ['all'])
    .action(async (url, options) => {
      const client = new VibecasterClient();
      const platforms = expandPlatforms(options.platform);

      console.log(chalk.cyan.bold('\n  Generating + posting from URL'));
      console.log(`  ${url}\n`);

      let job;
      try {
        job = await client.submitAndPoll('/cli/generate-from-url', {
          url,
          platforms,
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
