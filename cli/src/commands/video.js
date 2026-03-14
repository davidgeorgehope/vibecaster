import chalk from 'chalk';
import { VibecasterClient } from '../client.js';

export function registerVideo(program) {
  program
    .command('video <topic>')
    .description('Generate a multi-scene AI video from a topic')
    .option('-s, --style <style>', 'Video style: educational, storybook, social_media', 'educational')
    .option('-d, --duration <seconds>', 'Target duration: 16, 24, 32, or 48', '24')
    .option('-a, --aspect <ratio>', 'Aspect ratio: landscape or portrait', 'landscape')
    .option('--prompt <context>', 'Additional context or instructions')
    .action(async (topic, options) => {
      const client = new VibecasterClient();
      client.ensureAuth();

      console.log(chalk.cyan.bold(`\n  Generating video: "${topic}"`));
      console.log(`  Style: ${options.style}  Duration: ~${options.duration}s  Aspect: ${options.aspect}`);

      const job = await client.submitAndPoll('/cli/video', {
        topic,
        style: options.style,
        target_duration: parseInt(options.duration, 10),
        aspect_ratio: options.aspect,
        user_prompt: options.prompt || '',
      }, 1200);

      if (job.status === 'complete') {
        const r = job.result || {};
        if (r.video_job_id) {
          console.log(chalk.green.bold(`\n  Video ready!`));
          console.log(`  Video job ID: ${chalk.white(r.video_job_id)}`);
          if (r.duration) console.log(`  Duration: ${r.duration}s`);
          console.log(`\n  Download: ${client.apiUrl.replace('/api', '')}/api/video/jobs/${r.video_job_id}/download`);
        }
        console.log();
      }
    });
}
