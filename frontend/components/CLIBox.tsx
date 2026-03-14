'use client';

import { Terminal } from 'lucide-react';

export default function CLIBox() {
  return (
    <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-xl p-6">
      <div className="flex items-center gap-3 mb-6">
        <Terminal className="w-6 h-6 text-purple-500" />
        <h2 className="text-xl font-semibold text-white">CLI</h2>
      </div>

      <p className="text-sm text-gray-400 mb-4">
        Add Vibecaster as a skill for your AI coding agent, or use the CLI directly from the terminal.
      </p>

      {/* Agent Skill Install — the primary CTA */}
      <div className="mb-6 p-4 bg-purple-900/20 border border-purple-700/40 rounded-lg">
        <h3 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-2">Add to your AI agent</h3>
        <p className="text-sm text-gray-400 mb-3">
          Works with Claude Code, Codex, Cursor, and 38+ other agents.
        </p>
        <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-1">
          <p className="text-gray-500"># Install the Vibecaster skill</p>
          <p>npx skills add davidgeorgehope/vibecaster</p>
        </div>
        <p className="text-xs text-gray-500 mt-3">
          Then just tell your agent: &quot;Post to LinkedIn: Just shipped a new feature...&quot; — it handles the rest.
        </p>
      </div>

      {/* CLI Quick Start */}
      <div className="mb-6 p-4 bg-gray-800/50 border border-gray-700 rounded-lg">
        <h3 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-3">Or use the CLI directly</h3>
        <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-1">
          <p className="text-gray-500"># Run directly with npx (no install needed)</p>
          <p>npx vibecaster login</p>
          <p className="text-gray-500 mt-3"># Or install globally</p>
          <p>npm install -g vibecaster</p>
        </div>
      </div>

      {/* CLI Commands Guide */}
      <div className="border-t border-gray-700 pt-6">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <span className="text-2xl">⌨️</span> CLI Commands
        </h3>

        {/* Configure */}
        <div className="mb-6">
          <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-2">Configure</h4>
          <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-1">
            <p className="text-gray-500"># Login with your API key</p>
            <p>vibecaster login</p>
            <p className="text-gray-500 mt-1"># → API URL: https://vibecaster.ai/api</p>
            <p className="text-gray-500"># → API Key: vb_your_key_here</p>
          </div>
        </div>

        {/* Commands */}
        <div className="mb-6">
          <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-2">Commands</h4>
          <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-2">
            <div className="grid grid-cols-[200px_1fr] gap-x-4 gap-y-1">
              <span className="text-purple-400">vibecaster status</span>
              <span className="text-gray-400">Check connection & campaign status</span>
              <span className="text-purple-400">vibecaster campaign</span>
              <span className="text-gray-400">View your active campaign</span>
              <span className="text-purple-400">vibecaster create</span>
              <span className="text-gray-400">AI-generate a post from a prompt</span>
              <span className="text-purple-400">vibecaster generate</span>
              <span className="text-gray-400">Generate a post from URL (preview)</span>
              <span className="text-purple-400">vibecaster run</span>
              <span className="text-gray-400">Trigger immediate campaign run</span>
              <span className="text-purple-400">vibecaster post</span>
              <span className="text-gray-400">Post custom text/media directly</span>
              <span className="text-purple-400">vibecaster transcribe</span>
              <span className="text-gray-400">Transcribe audio/video file</span>
              <span className="text-purple-400">vibecaster video</span>
              <span className="text-gray-400">Generate multi-scene AI video</span>
              <span className="text-purple-400">vibecaster video-post</span>
              <span className="text-gray-400">Process video into platform posts</span>
              <span className="text-purple-400">vibecaster keys</span>
              <span className="text-gray-400">List your API keys</span>
            </div>
          </div>
        </div>

        {/* Direct Post */}
        <div className="mb-6">
          <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-2">Direct Posting</h4>
          <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-1">
            <p className="text-gray-500"># Post text to LinkedIn</p>
            <p>vibecaster post &quot;Your post text here&quot; --platform linkedin</p>
            <p className="text-gray-500 mt-3"># Post with an image</p>
            <p>vibecaster post &quot;Caption here&quot; --media image.png --platform linkedin</p>
            <p className="text-gray-500 mt-3"># Post with an AI-generated image</p>
            <p>vibecaster post &quot;Your text&quot; --imagegen &quot;neon abstract waves&quot;</p>
          </div>
        </div>

        {/* Transcribe & Video */}
        <div>
          <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-2">Transcribe & Video</h4>
          <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-1">
            <p className="text-gray-500"># Transcribe audio/video</p>
            <p>vibecaster transcribe recording.mp4 --output ./out</p>
            <p className="text-gray-500 mt-3"># Generate AI video</p>
            <p>vibecaster video &quot;How to deploy to Kubernetes&quot; --style educational</p>
            <p className="text-gray-500 mt-3"># Process video for social posting</p>
            <p>vibecaster video-post demo.mp4 --platform all</p>
          </div>
        </div>
      </div>
    </div>
  );
}
