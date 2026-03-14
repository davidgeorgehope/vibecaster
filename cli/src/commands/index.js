import { Command } from 'commander';
import { registerLogin } from './login.js';
import { registerStatus } from './status.js';
import { registerCreate } from './create.js';
import { registerPost } from './post.js';
import { registerGenerate } from './generate.js';
import { registerPostUrl } from './post-url.js';
import { registerCampaign } from './campaign.js';
import { registerRun } from './run.js';
import { registerJob } from './job.js';
import { registerKeys } from './keys.js';
import { registerTranscribe } from './transcribe.js';
import { registerVideo } from './video.js';
import { registerVideoPost } from './video-post.js';

export const program = new Command();

program
  .name('vibecaster')
  .description('Vibecaster - AI-powered social media automation CLI')
  .version('0.1.0');

registerLogin(program);
registerStatus(program);
registerCreate(program);
registerPost(program);
registerGenerate(program);
registerPostUrl(program);
registerCampaign(program);
registerRun(program);
registerJob(program);
registerKeys(program);
registerTranscribe(program);
registerVideo(program);
registerVideoPost(program);
