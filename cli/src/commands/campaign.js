import chalk from 'chalk';
import { VibecasterClient, ApiError } from '../client.js';
import { formatTimestamp, handleApiError } from '../util.js';

export function registerCampaign(program) {
  const campaignCmd = program
    .command('campaign')
    .description('View or manage campaign settings')
    .action(async () => {
      // Default action: show campaign details
      const client = new VibecasterClient();
      let data;
      try {
        data = await client.get('/campaign');
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.statusCode === 404) {
            console.log(chalk.yellow("No campaign configured. Use 'vibecaster campaign setup <prompt>' to create one."));
            return;
          }
          handleApiError(e);
        }
        throw e;
      }

      console.log(chalk.cyan.bold('\n  Campaign Details'));
      console.log(chalk.gray('  ' + '─'.repeat(40)));

      const isActive = data.is_active || false;
      console.log(`\n  Status:    ${isActive ? chalk.green('Active') : chalk.yellow('Inactive')}`);
      console.log(`  Schedule:  ${data.schedule_cron || 'Not set'}`);
      console.log(`  Media:     ${data.media_type || 'image'}`);
      console.log(`  Last run:  ${formatTimestamp(data.last_run || 0)}`);

      const prompt = data.user_prompt || '';
      if (prompt) {
        const display = prompt.length <= 200 ? prompt : prompt.slice(0, 200) + '...';
        console.log(`\n  Prompt:\n    ${display}`);
      }

      console.log();
    });

  campaignCmd
    .command('setup <prompt>')
    .description('Create or update campaign with a prompt')
    .action(async (prompt) => {
      const client = new VibecasterClient();

      console.log('Analyzing prompt and setting up campaign...');
      let result;
      try {
        result = await client.post('/setup', { prompt });
      } catch (e) {
        if (e instanceof ApiError) handleApiError(e);
        throw e;
      }

      console.log(chalk.green('Campaign configured!'));
      if (result.schedule_cron) {
        console.log(`  Schedule: ${result.schedule_cron}`);
      }
      if (result.media_type) {
        console.log(`  Media type: ${result.media_type}`);
      }
      console.log("\nUse 'vibecaster campaign activate' to start posting.");
    });

  campaignCmd
    .command('activate')
    .description('Activate the campaign scheduler')
    .action(async () => {
      const client = new VibecasterClient();

      let result;
      try {
        result = await client.post('/campaign/activate');
      } catch (e) {
        if (e instanceof ApiError) handleApiError(e);
        throw e;
      }

      console.log(chalk.green('Campaign activated!'));
      if (result.schedule_cron) {
        console.log(`  Schedule: ${result.schedule_cron}`);
      }
    });

  campaignCmd
    .command('deactivate')
    .description('Deactivate the campaign scheduler')
    .action(async () => {
      const client = new VibecasterClient();

      try {
        await client.post('/campaign/deactivate');
      } catch (e) {
        if (e instanceof ApiError) handleApiError(e);
        throw e;
      }

      console.log(chalk.yellow('Campaign deactivated.'));
    });
}
