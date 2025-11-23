'use client';

import { useState, useEffect } from 'react';
import { Sparkles, Loader2, Play, Trash2 } from 'lucide-react';

const API_URL = '/api';

interface PromptBoxProps {
  onActivate: (prompt: string) => Promise<void>;
  onRunNow: () => Promise<void>;
  token: string | null;
}

export default function PromptBox({ onActivate, onRunNow, token }: PromptBoxProps) {
  const [prompt, setPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [campaignConfigured, setCampaignConfigured] = useState(false);

  useEffect(() => {
    // Check if campaign is configured
    if (!token) return;

    fetch(`${API_URL}/api/campaign`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })
      .then(res => res.json())
      .then(data => {
        if (data.user_prompt) {
          setPrompt(data.user_prompt);
          setCampaignConfigured(true);
        }
      })
      .catch(() => {
        // Campaign not configured yet
        setCampaignConfigured(false);
      });
  }, [token]);

  const handleActivate = async () => {
    if (!prompt.trim()) return;

    setIsLoading(true);
    try {
      await onActivate(prompt);
      setCampaignConfigured(true);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRunNow = async () => {
    setIsRunning(true);
    try {
      await onRunNow();
    } finally {
      setIsRunning(false);
    }
  };

  const handleReset = async () => {
    if (!confirm('Are you sure you want to reset your campaign? This will clear all configuration.')) {
      return;
    }

    setIsDeleting(true);
    try {
      const response = await fetch(`${API_URL}/api/campaign`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to reset campaign');
      }

      setPrompt('');
      setCampaignConfigured(false);
    } catch (error) {
      console.error('Failed to reset campaign:', error);
      alert('Failed to reset campaign');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-6 hover:border-gray-700 transition-all">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-semibold text-white flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-purple-500" />
          Campaign Prompt
        </h3>
      </div>

      <div className="mb-4">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="What should I post about? (e.g., 'Post anime OpenTelemetry memes daily')"
          className="w-full h-40 bg-gray-800/50 border border-gray-700 rounded-lg p-4 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 resize-none"
        />
      </div>

      <div className="flex flex-col gap-3">
        <button
          onClick={handleActivate}
          disabled={isLoading || !prompt.trim()}
          className={`w-full py-3 px-4 rounded-lg font-medium transition-all bg-gradient-to-r from-purple-600 to-pink-600 hover:opacity-90 text-white neon-glow disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2`}
        >
          {isLoading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Analyzing...
            </>
          ) : (
            <>
              <Sparkles className="w-5 h-5" />
              {campaignConfigured ? 'Update Campaign' : 'Activate Campaign'}
            </>
          )}
        </button>

        {campaignConfigured && (
          <>
            <button
              onClick={handleRunNow}
              disabled={isRunning}
              className="w-full py-3 px-4 rounded-lg font-medium transition-all bg-gradient-to-r from-green-600 to-emerald-600 hover:opacity-90 text-white disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {isRunning ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <Play className="w-5 h-5" />
                  Run Now
                </>
              )}
            </button>

            <button
              onClick={handleReset}
              disabled={isDeleting}
              className="w-full py-3 px-4 rounded-lg font-medium transition-all bg-gradient-to-r from-red-600 to-rose-600 hover:opacity-90 text-white disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {isDeleting ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Resetting...
                </>
              ) : (
                <>
                  <Trash2 className="w-5 h-5" />
                  Reset Campaign
                </>
              )}
            </button>
          </>
        )}
      </div>

      {campaignConfigured && (
        <div className="mt-4 p-3 bg-green-900/20 border border-green-700/30 rounded-lg">
          <p className="text-sm text-green-400">
            ✓ Campaign is active and will run automatically based on schedule
          </p>
        </div>
      )}
    </div>
  );
}
