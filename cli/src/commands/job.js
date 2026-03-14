import chalk from 'chalk';
import { VibecasterClient, ApiError } from '../client.js';
import { formatTimestamp, handleApiError, displayJobResult } from '../util.js';

export function registerJob(program) {
  program
    .command('job <job_id>')
    .description('Check status of an async job')
    .action(async (jobId) => {
      const client = new VibecasterClient();

      let data;
      try {
        data = await client.get(`/cli/jobs/${jobId}`);
      } catch (e) {
        if (e instanceof ApiError) handleApiError(e);
        throw e;
      }

      const status = data.status || 'unknown';
      console.log(chalk.cyan.bold(`\n  Job ${jobId}`));
      console.log(`  Status: ${status}`);

      if (status === 'complete') {
        displayJobResult(data);
      } else if (status === 'failed') {
        console.log(chalk.red(`  Error: ${data.error || 'Unknown'}`));
      } else {
        console.log(`  Created: ${formatTimestamp(data.created_at)}`);
        console.log(`  Updated: ${formatTimestamp(data.updated_at)}`);
        console.log('  Still running... check again shortly.');
      }

      console.log();
    });
}
