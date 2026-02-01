'use client';

import { useState, useEffect, useCallback } from 'react';
import { Sparkles, Loader2, Play, Trash2, Image, Video, Shield, X, Plus, ChevronDown, ChevronRight } from 'lucide-react';

interface PromptBoxProps {
  onActivate: (prompt: string) => Promise<void>;
  onRunNow: () => Promise<void>;
  token: string | null;
}

export default function PromptBox({ onActivate, onRunNow, token }: PromptBoxProps) {
  const [prompt, setPrompt] = useState('');
  const [detectedMediaType, setDetectedMediaType] = useState<'image' | 'video'>('image');
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [campaignConfigured, setCampaignConfigured] = useState(false);

  // Excluded companies state
  const [excludeCompanies, setExcludeCompanies] = useState<string[]>([]);
  const [newCompany, setNewCompany] = useState('');
  const [filterOpen, setFilterOpen] = useState(false);
  const [isSavingFilter, setIsSavingFilter] = useState(false);

  const saveExcludeCompanies = useCallback(async (companies: string[]) => {
    if (!token) return;
    setIsSavingFilter(true);
    try {
      await fetch('/api/campaign/exclude-companies', {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ exclude_companies: companies }),
      });
    } catch (err) {
      console.error('Failed to save excluded companies:', err);
    } finally {
      setIsSavingFilter(false);
    }
  }, [token]);

  useEffect(() => {
    // Check if campaign is configured
    if (!token) return;

    fetch('/api/campaign', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })
      .then(res => res.json())
      .then(data => {
        if (data.user_prompt) {
          setPrompt(data.user_prompt);
          setCampaignConfigured(true);
          if (data.media_type) {
            setDetectedMediaType(data.media_type);
          }
          if (data.exclude_companies && Array.isArray(data.exclude_companies)) {
            setExcludeCompanies(data.exclude_companies);
          }
        }
      })
      .catch(() => {
        // Campaign not configured yet
        setCampaignConfigured(false);
      });
  }, [token]);

  const handleAddCompany = () => {
    const trimmed = newCompany.trim();
    if (!trimmed) return;
    if (excludeCompanies.some(c => c.toLowerCase() === trimmed.toLowerCase())) {
      setNewCompany('');
      return;
    }
    const updated = [...excludeCompanies, trimmed];
    setExcludeCompanies(updated);
    setNewCompany('');
    saveExcludeCompanies(updated);
  };

  const handleRemoveCompany = (company: string) => {
    const updated = excludeCompanies.filter(c => c !== company);
    setExcludeCompanies(updated);
    saveExcludeCompanies(updated);
  };

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
      const response = await fetch('/api/campaign', {
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
      setExcludeCompanies([]);
      setFilterOpen(false);
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

      {/* Media Type Info */}
      {campaignConfigured && (
        <div className="mb-4 flex items-center gap-2 text-sm text-gray-400">
          {detectedMediaType === 'video' ? (
            <>
              <Video className="w-4 h-4 text-purple-400" />
              <span>AI detected: <span className="text-purple-400">Video</span> (auto-detected from prompt)</span>
            </>
          ) : (
            <>
              <Image className="w-4 h-4 text-purple-400" />
              <span>AI detected: <span className="text-purple-400">Image</span> (default)</span>
            </>
          )}
        </div>
      )}

      {/* Content Filter - Excluded Companies */}
      {campaignConfigured && (
        <div className="mb-4 border border-gray-700/50 rounded-lg overflow-hidden">
          <button
            onClick={() => setFilterOpen(!filterOpen)}
            className="w-full flex items-center justify-between px-4 py-3 bg-gray-800/30 hover:bg-gray-800/50 transition-colors text-left"
          >
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-purple-400" />
              <span className="text-sm font-medium text-gray-300">Content Filter</span>
              {excludeCompanies.length > 0 && (
                <span className="text-xs bg-purple-600/30 text-purple-300 px-2 py-0.5 rounded-full">
                  {excludeCompanies.length}
                </span>
              )}
            </div>
            {filterOpen ? (
              <ChevronDown className="w-4 h-4 text-gray-500" />
            ) : (
              <ChevronRight className="w-4 h-4 text-gray-500" />
            )}
          </button>

          {filterOpen && (
            <div className="px-4 py-3 space-y-3">
              <p className="text-xs text-gray-500">
                Posts mentioning these companies will be blocked before publishing.
              </p>

              {/* Add company input */}
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newCompany}
                  onChange={(e) => setNewCompany(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddCompany();
                    }
                  }}
                  placeholder="Company name..."
                  className="flex-1 bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/20"
                />
                <button
                  onClick={handleAddCompany}
                  disabled={!newCompany.trim()}
                  className="px-3 py-2 bg-purple-600/20 border border-purple-500/30 text-purple-400 rounded-lg text-sm hover:bg-purple-600/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add
                </button>
              </div>

              {/* Company chips */}
              {excludeCompanies.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {excludeCompanies.map((company) => (
                    <span
                      key={company}
                      className="inline-flex items-center gap-1.5 px-3 py-1 bg-gray-800 border border-gray-700 rounded-full text-sm text-gray-300"
                    >
                      {company}
                      <button
                        onClick={() => handleRemoveCompany(company)}
                        className="text-gray-500 hover:text-red-400 transition-colors"
                        title={`Remove ${company}`}
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-gray-600 italic">No companies excluded yet.</p>
              )}

              {isSavingFilter && (
                <div className="flex items-center gap-1.5 text-xs text-gray-500">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Saving...
                </div>
              )}
            </div>
          )}
        </div>
      )}

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
