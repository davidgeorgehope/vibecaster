import chalk from 'chalk';
import { VibecasterClient, ApiError } from '../client.js';
import { formatTimestamp, handleApiError } from '../util.js';

export function registerStatus(program) {
  program
    .command('status')
    .description('Show campaign status and connected platforms')
    .action(async () => {
      const client = new VibecasterClient();

      let connections;
      try {
        connections = await client.get('/auth/status');
      } catch (e) {
        if (e instanceof ApiError) handleApiError(e);
        throw e;
      }

      console.log(chalk.cyan.bold('\n  Vibecaster Status'));
      console.log(chalk.gray('  ' + '─'.repeat(30)));

      console.log(chalk.white.bold('\n  Connections:'));
      for (const [platform, info] of Object.entries(connections)) {
        const connected = info.connected || false;
        const expired = info.expired || false;
        let name = platform.charAt(0).toUpperCase() + platform.slice(1);
        if (platform === 'youtube') name = 'YouTube';

        if (connected && !expired) {
          console.log(`    ${chalk.green('●')} ${name}`);
        } else if (connected && expired) {
          console.log(`    ${chalk.yellow('●')} ${name} (expired)`);
        } else {
          console.log(`    ${chalk.gray('○')} ${name}`);
        }
      }

      try {
        const campaign = await client.get('/campaign');
        console.log(chalk.white.bold('\n  Campaign:'));
        const isActive = campaign.is_active || false;
        if (isActive) {
          console.log(`    Status: ${chalk.green('Active')}`);
        } else {
          console.log(`    Status: ${chalk.yellow('Inactive')}`);
        }
        console.log(`    Schedule: ${campaign.schedule_cron || 'Not set'}`);
        const lastRun = campaign.last_run || 0;
        console.log(`    Last run: ${lastRun ? formatTimestamp(lastRun) : 'Never'}`);
      } catch {
        console.log(chalk.yellow('\n  Campaign: Not configured'));
      }

      console.log();
    });
}
