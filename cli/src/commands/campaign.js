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

  campaignCmd
    .command('edit')
    .description('Edit campaign settings')
    .option('--persona <text>', 'Set refined persona')
    .option('--style <text>', 'Set visual style')
    .option('--media <type>', 'Set media type: image or video')
    .option('--schedule <frequency>', 'Set frequency: daily, twice-daily, 3x-daily, weekly, 3x-weekly')
    .option('--time <HH:MM>', 'Set posting time (UTC)')
    .option('--exclude <companies>', 'Set excluded companies (comma-separated)')
    .action(async (options) => {
      const client = new VibecasterClient();

      const settings = {};
      if (options.persona) settings.refined_persona = options.persona;
      if (options.style) settings.visual_style = options.style;
      if (options.media) settings.media_type = options.media;
      if (options.exclude) settings.excluded_companies = options.exclude.split(',').map(s => s.trim());

      // Convert schedule + time to cron expression
      if (options.schedule || options.time) {
        const time = options.time || '09:00';
        const [hour, minute] = time.split(':').map(Number);
        const scheduleMap = {
          'daily': `${minute} ${hour} * * *`,
          'twice-daily': `${minute} ${hour},${(hour + 12) % 24} * * *`,
          '3x-daily': `${minute} ${hour},${(hour + 8) % 24},${(hour + 16) % 24} * * *`,
          'weekly': `${minute} ${hour} * * 1`,
          '3x-weekly': `${minute} ${hour} * * 1,3,5`,
        };
        const freq = options.schedule || 'daily';
        if (scheduleMap[freq]) {
          settings.schedule_cron = scheduleMap[freq];
        } else {
          console.error(chalk.red(`  Invalid schedule: ${freq}`));
          console.error(`  Valid options: daily, twice-daily, 3x-daily, weekly, 3x-weekly`);
          return;
        }
      }

      if (Object.keys(settings).length === 0) {
        console.log(chalk.yellow('  No settings specified. Use --persona, --style, --media, --schedule, --time, or --exclude.'));
        return;
      }

      try {
        await client.put('/campaign/settings', settings);
      } catch (e) {
        if (e instanceof ApiError) handleApiError(e);
        throw e;
      }

      console.log(chalk.green('  Campaign settings updated!'));
      for (const [key, value] of Object.entries(settings)) {
        console.log(`  ${key}: ${Array.isArray(value) ? value.join(', ') : value}`);
      }
    });

  campaignCmd
    .command('reset')
    .description('Delete and reset campaign entirely')
    .action(async () => {
      const client = new VibecasterClient();

      try {
        await client.del('/campaign');
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.statusCode === 404) {
            console.log(chalk.yellow('  No campaign to reset.'));
            return;
          }
          handleApiError(e);
        }
        throw e;
      }

      console.log(chalk.green('  Campaign reset successfully.'));
    });
}
