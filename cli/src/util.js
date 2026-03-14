import chalk from 'chalk';

export function formatTimestamp(ts) {
  if (!ts) return 'Never';
  const d = new Date(ts * 1000);
  return d.toISOString().replace('T', ' ').slice(0, 16);
}

export function handleApiError(e) {
  console.error(chalk.red(`API Error (${e.statusCode}): ${e.detail}`));
  process.exit(1);
}

export function displayJobResult(job) {
  const result = job.result || {};
  if (!result || Object.keys(result).length === 0) return;

  const xPost = result.x_post || '';
  const linkedinPost = result.linkedin_post || '';
  const hasImage = result.has_image || false;
  const posted = result.posted || [];
  const errors = result.errors || {};

  if (xPost) {
    console.log(chalk.cyan.bold('\n  [TWITTER/X]'));
    console.log(chalk.gray('  ' + '─'.repeat(40)));
    for (const line of xPost.split('\n')) {
      console.log(`  ${line}`);
    }
  }

  if (linkedinPost) {
    console.log(chalk.blue.bold('\n  [LINKEDIN]'));
    console.log(chalk.gray('  ' + '─'.repeat(40)));
    for (const line of linkedinPost.split('\n')) {
      console.log(`  ${line}`);
    }
  }

  if (hasImage) {
    console.log(`\n  ${chalk.green('🖼')}  Image generated`);
  }

  if (posted.length > 0) {
    console.log();
    for (const p of posted) {
      console.log(`  ${chalk.green('✓')} Posted to ${p}`);
    }
  }

  if (Object.keys(errors).length > 0) {
    for (const [platform, error] of Object.entries(errors)) {
      console.log(`  ${chalk.red('✗')} ${platform}: ${error}`);
    }
  }

  console.log();
}

export function expandPlatforms(platforms) {
  const result = [];
  for (const p of platforms) {
    if (p === 'all') {
      result.push('twitter', 'linkedin');
    } else {
      result.push(p);
    }
  }
  return [...new Set(result)];
}
