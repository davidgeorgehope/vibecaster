import chalk from 'chalk';
import ora from 'ora';
import { readFileSync } from 'fs';
import { basename } from 'path';
import { VibecasterClient } from '../client.js';

export function registerTranscribe(program) {
  program
    .command('transcribe <file>')
    .description('Transcribe audio/video file — get transcript, summary, and blog post')
    .option('-o, --output <dir>', 'Save output to files in this directory')
    .action(async (file, options) => {
      const client = new VibecasterClient();
      client.ensureAuth();

      console.log(chalk.cyan.bold(`\n  Transcribing: ${file}`));

      // Read the file
      let fileBuffer;
      try {
        fileBuffer = readFileSync(file);
      } catch (err) {
        console.error(chalk.red(`  Error: Could not read file: ${err.message}`));
        process.exitCode = 1;
        return;
      }

      const fileName = basename(file);
      let mimeType = 'application/octet-stream';
      const ext = file.toLowerCase().split('.').pop();
      const mimeMap = {
        mp3: 'audio/mpeg', wav: 'audio/wav', aac: 'audio/aac',
        ogg: 'audio/ogg', flac: 'audio/flac', aiff: 'audio/aiff',
        mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime',
        m4v: 'video/x-m4v',
      };
      if (mimeMap[ext]) mimeType = mimeMap[ext];

      // Submit job
      let result;
      try {
        const formData = new FormData();
        formData.append('file', new Blob([fileBuffer], { type: mimeType }), fileName);

        const response = await fetch(`${client.apiUrl}/cli/transcribe`, {
          method: 'POST',
          headers: { 'X-API-Key': client.apiKey },
          body: formData,
          signal: AbortSignal.timeout(30000),
        });

        if (response.status >= 400) {
          let detail;
          try {
            const json = await response.json();
            detail = json.detail || response.statusText;
          } catch {
            detail = response.statusText;
          }
          console.error(chalk.red(`  Error: ${detail}`));
          process.exitCode = 1;
          return;
        }
        result = await response.json();
      } catch (err) {
        if (err.name === 'TimeoutError') {
          console.error(chalk.red('  Error: Request timed out'));
        } else {
          console.error(chalk.red(`  Error: Could not connect to ${client.apiUrl}`));
        }
        process.exitCode = 1;
        return;
      }

      const jobId = result.job_id;
      if (!jobId) {
        console.error(chalk.red('  Error: No job ID returned'));
        process.exitCode = 1;
        return;
      }

      // Poll for completion
      const statusLabels = {
        pending: 'Queued',
        uploading: 'Uploading to Gemini',
        transcribing: 'Transcribing audio',
        summarizing: 'Generating summary',
        generating_blog: 'Writing blog post',
      };

      const spinner = ora({ text: 'Starting...', color: 'cyan' }).start();
      const start = Date.now();

      while ((Date.now() - start) / 1000 < 600) {
        let job;
        try {
          job = await client.get(`/cli/jobs/${jobId}`);
        } catch {
          await new Promise((r) => setTimeout(r, 2000));
          continue;
        }

        const status = job.status || 'unknown';

        if (status === 'complete') {
          spinner.succeed('Transcription complete!');
          const r = job.result || {};

          if (options.output) {
            const { writeFileSync, mkdirSync } = await import('fs');
            const { join } = await import('path');
            mkdirSync(options.output, { recursive: true });

            if (r.transcript) writeFileSync(join(options.output, 'transcript.txt'), r.transcript);
            if (r.summary) writeFileSync(join(options.output, 'summary.txt'), r.summary);
            if (r.blog_post) writeFileSync(join(options.output, 'blog_post.md'), r.blog_post);
            console.log(chalk.green(`\n  Files saved to ${options.output}/`));
            console.log(`    transcript.txt, summary.txt, blog_post.md`);
          } else {
            if (r.transcript) {
              console.log(chalk.cyan.bold('\n  [TRANSCRIPT]'));
              console.log(chalk.gray('  ' + '-'.repeat(60)));
              console.log(`  ${r.transcript.slice(0, 2000)}${r.transcript.length > 2000 ? '...' : ''}`);
            }
            if (r.summary) {
              console.log(chalk.blue.bold('\n  [SUMMARY]'));
              console.log(chalk.gray('  ' + '-'.repeat(60)));
              console.log(`  ${r.summary}`);
            }
            if (r.blog_post) {
              console.log(chalk.green.bold('\n  [BLOG POST]'));
              console.log(chalk.gray('  ' + '-'.repeat(60)));
              console.log(`  ${r.blog_post.slice(0, 3000)}${r.blog_post.length > 3000 ? '...' : ''}`);
            }
          }
          console.log();
          return;
        } else if (status === 'failed') {
          spinner.fail(`Failed: ${job.error || 'Unknown'}`);
          process.exitCode = 1;
          return;
        }

        spinner.text = `${statusLabels[status] || status}...`;
        await new Promise((r) => setTimeout(r, 2000));
      }

      spinner.warn(`Timed out. Job ID: ${jobId}`);
      console.log(`  Check later: vibecaster job ${jobId}`);
    });
}
