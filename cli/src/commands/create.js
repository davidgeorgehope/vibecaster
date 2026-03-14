import chalk from 'chalk';
import { VibecasterClient, ApiError } from '../client.js';
import { handleApiError, displayJobResult, expandPlatforms } from '../util.js';

export function registerCreate(program) {
  program
    .command('create <prompt>')
    .description('Create a post from a text prompt')
    .option('-p, --post <platform...>', 'Post to platform(s): twitter, linkedin, all. Omit for preview only.')
    .option('--no-image', 'Skip image generation')
    .action(async (prompt, options) => {
      const client = new VibecasterClient();
      const platforms = options.post ? expandPlatforms(options.post) : [];

      const mode = platforms.length > 0 ? 'Generating + posting' : 'Generating preview';
      console.log(chalk.cyan.bold(`\n  ${mode}`));
      console.log(`  Prompt: ${prompt}\n`);

      let job;
      try {
        job = await client.submitAndPoll('/cli/create-post', {
          prompt,
          platforms,
          media_type: options.image === false ? 'none' : 'image',
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
