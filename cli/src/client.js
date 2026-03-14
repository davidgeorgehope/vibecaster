import { loadConfig } from './config.js';
import chalk from 'chalk';
import ora from 'ora';

export class ApiError extends Error {
  constructor(statusCode, detail) {
    super(`HTTP ${statusCode}: ${detail}`);
    this.statusCode = statusCode;
    this.detail = detail;
  }
}

export class VibecasterClient {
  constructor() {
    const config = loadConfig();
    this.apiUrl = config.api_url || 'https://vibecaster.ai/api';
    this.apiKey = config.api_key;
  }

  ensureAuth() {
    if (!this.apiKey) {
      console.error(chalk.red("Error: Not logged in. Run 'vibecaster login' first."));
      process.exit(1);
    }
  }

  headers(extraHeaders = {}) {
    return {
      'X-API-Key': this.apiKey,
      'Content-Type': 'application/json',
      ...extraHeaders,
    };
  }

  async request(method, path, options = {}) {
    this.ensureAuth();
    const url = `${this.apiUrl}${path}`;
    const { headers: extraHeaders, ...fetchOptions } = options;
    const headers = this.headers(extraHeaders);

    let response;
    try {
      response = await fetch(url, {
        method,
        headers,
        signal: AbortSignal.timeout(30000),
        ...fetchOptions,
      });
    } catch (err) {
      if (err.name === 'TimeoutError') {
        console.error(chalk.red('Error: Request timed out'));
        process.exit(1);
      }
      console.error(chalk.red(`Error: Could not connect to ${this.apiUrl}`));
      process.exit(1);
    }

    if (response.status >= 400) {
      let detail;
      try {
        const json = await response.json();
        detail = json.detail || response.statusText;
      } catch {
        detail = response.statusText;
      }
      throw new ApiError(response.status, detail);
    }

    if (response.status === 204) return {};

    const text = await response.text();
    if (!text) return {};
    return JSON.parse(text);
  }

  async get(path, options) {
    return this.request('GET', path, options);
  }

  async post(path, body, options = {}) {
    return this.request('POST', path, {
      body: JSON.stringify(body),
      ...options,
    });
  }

  async put(path, body, options = {}) {
    return this.request('PUT', path, {
      body: JSON.stringify(body),
      ...options,
    });
  }

  async del(path, options) {
    return this.request('DELETE', path, options);
  }

  async submitAndPoll(endpoint, payload, timeout = 300) {
    const result = await this.post(endpoint, payload);
    const jobId = result.job_id;
    if (!jobId) return result;

    const statusLabels = {
      pending: 'Queued',
      generating_text: 'Generating post text',
      generating_image: 'Generating image',
      generating: 'Generating content',
      posting: 'Posting to platforms',
      complete: 'Done',
      failed: 'Failed',
    };

    const spinner = ora({ text: 'Starting...', color: 'cyan' }).start();
    const start = Date.now();

    while ((Date.now() - start) / 1000 < timeout) {
      let job;
      try {
        job = await this.get(`/cli/jobs/${jobId}`);
      } catch {
        await sleep(2000);
        continue;
      }

      const jobStatus = job.status || 'unknown';
      const label = statusLabels[jobStatus] || jobStatus;

      if (jobStatus === 'complete') {
        spinner.succeed(label);
        return job;
      } else if (jobStatus === 'failed') {
        spinner.fail(`${label}: ${job.error || 'Unknown error'}`);
        return job;
      }

      spinner.text = `${label}...`;
      await sleep(1500);
    }

    spinner.warn(`Timed out after ${timeout}s. Job ID: ${jobId}`);
    console.log(`  Check later: vibecaster job ${jobId}`);
    return { job_id: jobId, status: 'timeout' };
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
