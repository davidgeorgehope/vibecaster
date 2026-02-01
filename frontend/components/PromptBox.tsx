'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Sparkles, Loader2, Play, Trash2, Image, Video,
  X, Plus, ChevronDown, ChevronRight, Save,
  Power, PowerOff, Pencil, Eye, Clock, Shield, Zap
} from 'lucide-react';

interface PromptBoxProps {
  onRunNow: () => Promise<void>;
  token: string | null;
  showNotification: (type: 'success' | 'error' | 'info', message: string) => void;
}

interface CampaignData {
  user_prompt: string;
  refined_persona: string;
  visual_style: string;
  schedule_cron: string;
  media_type: string;
  exclude_companies: string[];
  is_active: boolean;
  schedule_description?: string;
}

// Map common cron expressions to friendly labels
function cronToFriendly(cron: string): { frequency: string; time: string } {
  const parts = cron.split(' ');
  if (parts.length !== 5) return { frequency: 'custom', time: '9:00 AM' };

  const [minute, hour, , , dayOfWeek] = parts;
  const hours = hour.split(',');
  const timeStr = hours
    .map((h) => {
      const hr = parseInt(h);
      const ampm = hr >= 12 ? 'PM' : 'AM';
      const displayHr = hr === 0 ? 12 : hr > 12 ? hr - 12 : hr;
      return `${displayHr}:${minute.padStart(2, '0')} ${ampm}`;
    })
    .join(' & ');

  if (hours.length >= 3) return { frequency: 'three_daily', time: timeStr };
  if (hours.length === 2) return { frequency: 'twice_daily', time: timeStr };
  if (dayOfWeek === '1') return { frequency: 'weekly', time: timeStr };
  if (dayOfWeek === '1,3,5') return { frequency: 'three_weekly', time: timeStr };
  if (dayOfWeek !== '*') return { frequency: 'custom', time: timeStr };
  return { frequency: 'daily', time: timeStr };
}

function friendlyToCron(frequency: string, hour: number, minute: number): string {
  switch (frequency) {
    case 'twice_daily': {
      const evening = (hour + 8) % 24;
      return `${minute} ${hour},${evening} * * *`;
    }
    case 'three_daily': {
      const mid = (hour + 5) % 24;
      const evening = (hour + 10) % 24;
      return `${minute} ${hour},${mid},${evening} * * *`;
    }
    case 'weekly':
      return `${minute} ${hour} * * 1`;
    case 'three_weekly':
      return `${minute} ${hour} * * 1,3,5`;
    case 'daily':
    default:
      return `${minute} ${hour} * * *`;
  }
}

const FREQUENCY_OPTIONS = [
  { value: 'daily', label: 'Daily' },
  { value: 'twice_daily', label: 'Twice Daily' },
  { value: 'three_daily', label: 'Three Times Daily' },
  { value: 'three_weekly', label: '3x / Week' },
  { value: 'weekly', label: 'Weekly' },
];

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => {
  const ampm = i >= 12 ? 'PM' : 'AM';
  const display = i === 0 ? 12 : i > 12 ? i - 12 : i;
  return { value: i, label: `${display}:00 ${ampm}` };
});

export default function PromptBox({ onRunNow, token, showNotification }: PromptBoxProps) {
  const [prompt, setPrompt] = useState('');
  const [campaign, setCampaign] = useState<CampaignData | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isActivating, setIsActivating] = useState(false);
  const [isSavingOverrides, setIsSavingOverrides] = useState(false);

  // Editable inferred settings
  const [editPersona, setEditPersona] = useState(false);
  const [editVisualStyle, setEditVisualStyle] = useState(false);
  const [persona, setPersona] = useState('');
  const [visualStyle, setVisualStyle] = useState('');
  const [mediaType, setMediaType] = useState<'image' | 'video'>('image');
  const [frequency, setFrequency] = useState('daily');
  const [scheduleHour, setScheduleHour] = useState(9);
  const [excludeCompanies, setExcludeCompanies] = useState<string[]>([]);
  const [newCompany, setNewCompany] = useState('');
  const [filterOpen, setFilterOpen] = useState(false);

  // Track if user has unsaved overrides
  const [hasOverrides, setHasOverrides] = useState(false);

  // Load existing campaign
  const loadCampaign = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch('/api/campaign', {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data = await res.json();

      setCampaign(data);
      setPrompt(data.user_prompt || '');
      setPersona(data.refined_persona || '');
      setVisualStyle(data.visual_style || '');
      setMediaType(data.media_type === 'video' ? 'video' : 'image');
      setExcludeCompanies(data.exclude_companies || []);

      const { frequency: freq } = cronToFriendly(data.schedule_cron || '0 9 * * *');
      setFrequency(freq);
      const parts = (data.schedule_cron || '0 9 * * *').split(' ');
      setScheduleHour(parseInt(parts[1]?.split(',')[0] || '9'));
    } catch {
      // No campaign yet
    }
  }, [token]);

  useEffect(() => {
    loadCampaign();
  }, [loadCampaign]);

  // Save prompt + run AI inference
  const handleSaveAndInfer = async () => {
    if (!prompt.trim() || !token) return;
    setIsAnalyzing(true);

    try {
      const res = await fetch('/api/setup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ user_prompt: prompt }),
      });

      if (!res.ok) throw new Error('Failed to analyze prompt');
      const data = await res.json();
      const c = data.campaign;

      const newCampaign: CampaignData = {
        user_prompt: c.user_prompt,
        refined_persona: c.refined_persona,
        visual_style: c.visual_style,
        schedule_cron: c.schedule_cron,
        media_type: c.media_type,
        exclude_companies: c.exclude_companies || [],
        is_active: false, // Save doesn't activate
        schedule_description: c.schedule_description,
      };

      setCampaign(newCampaign);
      setPersona(c.refined_persona);
      setVisualStyle(c.visual_style);
      setMediaType(c.media_type === 'video' ? 'video' : 'image');
      setExcludeCompanies(c.exclude_companies || []);

      const { frequency: freq } = cronToFriendly(c.schedule_cron || '0 9 * * *');
      setFrequency(freq);
      const parts = (c.schedule_cron || '0 9 * * *').split(' ');
      setScheduleHour(parseInt(parts[1]?.split(',')[0] || '9'));

      setHasOverrides(false);
      showNotification('success', 'AI analyzed your prompt and inferred settings');
    } catch (error) {
      console.error(error);
      showNotification('error', 'Failed to analyze prompt');
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Save overrides
  const handleSaveOverrides = async () => {
    if (!token) return;
    setIsSavingOverrides(true);

    try {
      const cronExpr = friendlyToCron(frequency, scheduleHour, 0);
      const res = await fetch('/api/campaign/settings', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          refined_persona: persona,
          visual_style: visualStyle,
          media_type: mediaType,
          schedule_cron: cronExpr,
          exclude_companies: excludeCompanies,
        }),
      });

      if (!res.ok) throw new Error('Failed to save overrides');
      const data = await res.json();

      setCampaign((prev) =>
        prev
          ? {
              ...prev,
              refined_persona: data.campaign.refined_persona,
              visual_style: data.campaign.visual_style,
              media_type: data.campaign.media_type,
              schedule_cron: data.campaign.schedule_cron,
              exclude_companies: data.campaign.exclude_companies,
            }
          : prev
      );

      setHasOverrides(false);
      showNotification('success', 'Settings saved');
    } catch (error) {
      console.error(error);
      showNotification('error', 'Failed to save settings');
    } finally {
      setIsSavingOverrides(false);
    }
  };

  // Activate
  const handleActivate = async () => {
    if (!token) return;
    setIsActivating(true);
    try {
      const res = await fetch('/api/campaign/activate', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to activate');
      }
      setCampaign((prev) => (prev ? { ...prev, is_active: true } : prev));
      showNotification('success', 'Campaign activated! Posts will run on schedule.');
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Failed to activate';
      showNotification('error', msg);
    } finally {
      setIsActivating(false);
    }
  };

  // Deactivate
  const handleDeactivate = async () => {
    if (!token) return;
    setIsActivating(true);
    try {
      const res = await fetch('/api/campaign/deactivate', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to deactivate');
      setCampaign((prev) => (prev ? { ...prev, is_active: false } : prev));
      showNotification('info', 'Campaign deactivated');
    } catch {
      showNotification('error', 'Failed to deactivate');
    } finally {
      setIsActivating(false);
    }
  };

  // Run now
  const handleRunNow = async () => {
    setIsRunning(true);
    try {
      await onRunNow();
    } finally {
      setIsRunning(false);
    }
  };

  // Reset
  const handleReset = async () => {
    if (!confirm('Reset campaign? This clears all configuration.')) return;
    setIsDeleting(true);
    try {
      const res = await fetch('/api/campaign', {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to reset');
      setPrompt('');
      setCampaign(null);
      setPersona('');
      setVisualStyle('');
      setMediaType('image');
      setFrequency('daily');
      setScheduleHour(9);
      setExcludeCompanies([]);
      setHasOverrides(false);
      showNotification('info', 'Campaign reset');
    } catch {
      showNotification('error', 'Failed to reset campaign');
    } finally {
      setIsDeleting(false);
    }
  };

  // Company tag helpers
  const handleAddCompany = () => {
    const trimmed = newCompany.trim();
    if (!trimmed) return;
    if (excludeCompanies.some((c) => c.toLowerCase() === trimmed.toLowerCase())) {
      setNewCompany('');
      return;
    }
    setExcludeCompanies((prev) => [...prev, trimmed]);
    setNewCompany('');
    setHasOverrides(true);
  };

  const handleRemoveCompany = (company: string) => {
    setExcludeCompanies((prev) => prev.filter((c) => c !== company));
    setHasOverrides(true);
  };

  const hasCampaign = campaign && campaign.user_prompt;

  return (
    <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-xl overflow-hidden">
      {/* ─── STEP 1: Prompt ─── */}
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-semibold text-white flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-purple-500" />
            Campaign Prompt
          </h3>
          {hasCampaign && (
            <span
              className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                campaign.is_active
                  ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                  : 'bg-gray-700/50 text-gray-400 border border-gray-600/30'
              }`}
            >
              {campaign.is_active ? '● Active' : '○ Inactive'}
            </span>
          )}
        </div>

        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="What should I post about? (e.g., 'Post anime OpenTelemetry memes twice daily')"
          className="w-full h-32 bg-gray-800/50 border border-gray-700 rounded-lg p-4 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 resize-none"
        />

        <button
          onClick={handleSaveAndInfer}
          disabled={isAnalyzing || !prompt.trim()}
          className="mt-3 w-full py-3 px-4 rounded-lg font-medium transition-all bg-gradient-to-r from-purple-600 to-pink-600 hover:opacity-90 text-white disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {isAnalyzing ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Analyzing with AI...
            </>
          ) : (
            <>
              <Zap className="w-5 h-5" />
              {hasCampaign ? 'Re-Analyze Prompt' : 'Save & Analyze'}
            </>
          )}
        </button>
      </div>

      {/* ─── STEP 2: Inferred Settings ─── */}
      {hasCampaign && (
        <>
          <div className="border-t border-gray-800 p-6 space-y-5">
            <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
              Inferred Settings
            </h4>

            {/* Persona */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-sm font-medium text-gray-300">Persona</label>
                <button
                  onClick={() => { setEditPersona(!editPersona); }}
                  className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1"
                >
                  {editPersona ? <Eye className="w-3.5 h-3.5" /> : <Pencil className="w-3.5 h-3.5" />}
                  {editPersona ? 'Preview' : 'Edit'}
                </button>
              </div>
              {editPersona ? (
                <textarea
                  value={persona}
                  onChange={(e) => { setPersona(e.target.value); setHasOverrides(true); }}
                  className="w-full h-28 bg-gray-800/50 border border-gray-700 rounded-lg p-3 text-sm text-white focus:outline-none focus:border-purple-500 resize-none"
                />
              ) : (
                <div className="bg-gray-800/30 border border-gray-700/50 rounded-lg p-3 text-sm text-gray-300 max-h-28 overflow-y-auto whitespace-pre-wrap">
                  {persona || <span className="text-gray-600 italic">Not set</span>}
                </div>
              )}
            </div>

            {/* Visual Style */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-sm font-medium text-gray-300">Visual Style</label>
                <button
                  onClick={() => { setEditVisualStyle(!editVisualStyle); }}
                  className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1"
                >
                  {editVisualStyle ? <Eye className="w-3.5 h-3.5" /> : <Pencil className="w-3.5 h-3.5" />}
                  {editVisualStyle ? 'Preview' : 'Edit'}
                </button>
              </div>
              {editVisualStyle ? (
                <textarea
                  value={visualStyle}
                  onChange={(e) => { setVisualStyle(e.target.value); setHasOverrides(true); }}
                  className="w-full h-24 bg-gray-800/50 border border-gray-700 rounded-lg p-3 text-sm text-white focus:outline-none focus:border-purple-500 resize-none"
                />
              ) : (
                <div className="bg-gray-800/30 border border-gray-700/50 rounded-lg p-3 text-sm text-gray-300 max-h-24 overflow-y-auto whitespace-pre-wrap">
                  {visualStyle || <span className="text-gray-600 italic">Not set</span>}
                </div>
              )}
            </div>

            {/* Media Type Toggle */}
            <div>
              <label className="text-sm font-medium text-gray-300 mb-2 block">Media Type</label>
              <div className="flex gap-2">
                <button
                  onClick={() => { setMediaType('image'); setHasOverrides(true); }}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all border ${
                    mediaType === 'image'
                      ? 'bg-purple-600/20 border-purple-500/50 text-purple-300'
                      : 'bg-gray-800/30 border-gray-700/50 text-gray-400 hover:border-gray-600'
                  }`}
                >
                  <Image className="w-4 h-4" /> Image
                </button>
                <button
                  onClick={() => { setMediaType('video'); setHasOverrides(true); }}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all border ${
                    mediaType === 'video'
                      ? 'bg-purple-600/20 border-purple-500/50 text-purple-300'
                      : 'bg-gray-800/30 border-gray-700/50 text-gray-400 hover:border-gray-600'
                  }`}
                >
                  <Video className="w-4 h-4" /> Video
                </button>
              </div>
            </div>

            {/* Schedule */}
            <div>
              <label className="text-sm font-medium text-gray-300 mb-2 flex items-center gap-1.5">
                <Clock className="w-4 h-4 text-gray-400" /> Schedule
              </label>
              <div className="flex gap-2">
                <select
                  value={frequency}
                  onChange={(e) => { setFrequency(e.target.value); setHasOverrides(true); }}
                  className="flex-1 bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500 appearance-none cursor-pointer"
                >
                  {FREQUENCY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <select
                  value={scheduleHour}
                  onChange={(e) => { setScheduleHour(parseInt(e.target.value)); setHasOverrides(true); }}
                  className="flex-1 bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500 appearance-none cursor-pointer"
                >
                  {HOUR_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Excluded Companies */}
            <div className="border border-gray-700/50 rounded-lg overflow-hidden">
              <button
                onClick={() => setFilterOpen(!filterOpen)}
                className="w-full flex items-center justify-between px-4 py-3 bg-gray-800/30 hover:bg-gray-800/50 transition-colors text-left"
              >
                <div className="flex items-center gap-2">
                  <Shield className="w-4 h-4 text-purple-400" />
                  <span className="text-sm font-medium text-gray-300">Excluded Companies</span>
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
                    AI-inferred competitors. Posts mentioning these will be blocked.
                  </p>

                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newCompany}
                      onChange={(e) => setNewCompany(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') { e.preventDefault(); handleAddCompany(); }
                      }}
                      placeholder="Add company..."
                      className="flex-1 bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/20"
                    />
                    <button
                      onClick={handleAddCompany}
                      disabled={!newCompany.trim()}
                      className="px-3 py-2 bg-purple-600/20 border border-purple-500/30 text-purple-400 rounded-lg text-sm hover:bg-purple-600/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                    >
                      <Plus className="w-3.5 h-3.5" /> Add
                    </button>
                  </div>

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
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-600 italic">No companies excluded.</p>
                  )}
                </div>
              )}
            </div>

            {/* Save Overrides Button */}
            {hasOverrides && (
              <button
                onClick={handleSaveOverrides}
                disabled={isSavingOverrides}
                className="w-full py-2.5 px-4 rounded-lg font-medium transition-all bg-gray-700 hover:bg-gray-600 text-white border border-gray-600 flex items-center justify-center gap-2 text-sm"
              >
                {isSavingOverrides ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Saving...</>
                ) : (
                  <><Save className="w-4 h-4" /> Save Changes</>
                )}
              </button>
            )}
          </div>

          {/* ─── STEP 3: Activate / Run / Reset ─── */}
          <div className="border-t border-gray-800 p-6 space-y-3">
            {!campaign.is_active ? (
              <button
                onClick={handleActivate}
                disabled={isActivating}
                className="w-full py-3 px-4 rounded-lg font-medium transition-all bg-gradient-to-r from-green-600 to-emerald-600 hover:opacity-90 text-white disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isActivating ? (
                  <><Loader2 className="w-5 h-5 animate-spin" /> Activating...</>
                ) : (
                  <><Power className="w-5 h-5" /> Activate Campaign</>
                )}
              </button>
            ) : (
              <div className="flex gap-3">
                <button
                  onClick={handleDeactivate}
                  disabled={isActivating}
                  className="flex-1 py-3 px-4 rounded-lg font-medium transition-all bg-gray-700 hover:bg-gray-600 text-white border border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isActivating ? (
                    <><Loader2 className="w-5 h-5 animate-spin" /> ...</>
                  ) : (
                    <><PowerOff className="w-5 h-5" /> Deactivate</>
                  )}
                </button>
                <button
                  onClick={handleRunNow}
                  disabled={isRunning}
                  className="flex-1 py-3 px-4 rounded-lg font-medium transition-all bg-gradient-to-r from-green-600 to-emerald-600 hover:opacity-90 text-white disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isRunning ? (
                    <><Loader2 className="w-5 h-5 animate-spin" /> Running...</>
                  ) : (
                    <><Play className="w-5 h-5" /> Run Now</>
                  )}
                </button>
              </div>
            )}

            {/* Run Now when inactive */}
            {!campaign.is_active && (
              <button
                onClick={handleRunNow}
                disabled={isRunning}
                className="w-full py-3 px-4 rounded-lg font-medium transition-all bg-gray-700 hover:bg-gray-600 text-white border border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isRunning ? (
                  <><Loader2 className="w-5 h-5 animate-spin" /> Running...</>
                ) : (
                  <><Play className="w-5 h-5" /> Run Now (One-Time)</>
                )}
              </button>
            )}

            <button
              onClick={handleReset}
              disabled={isDeleting}
              className="w-full py-2.5 px-4 rounded-lg font-medium transition-all text-red-400 hover:bg-red-900/20 border border-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-sm"
            >
              {isDeleting ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Resetting...</>
              ) : (
                <><Trash2 className="w-4 h-4" /> Reset Campaign</>
              )}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
