'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Video, Send, Loader2, Play, Download, History, AlertCircle, Check, Image, Film, Scissors, Sparkles } from 'lucide-react';

interface VideoBuilderProps {
  token: string | null;
  showNotification: (type: 'success' | 'error' | 'info', message: string) => void;
}

interface Scene {
  scene_number: number;
  narration: string;
  status: 'pending' | 'generating_image' | 'generating_video' | 'complete' | 'error';
}

interface VideoJob {
  id: number;
  job_id: string;
  status: string;
  title: string;
  created_at: number;
  updated_at: number;
  error_message?: string;
}

type GenerationPhase = 'idle' | 'planning' | 'generating' | 'stitching' | 'complete' | 'error';

const STYLE_OPTIONS = [
  { value: 'educational', label: 'Educational', description: 'Clear, instructive explainer' },
  { value: 'storybook', label: 'Storybook', description: 'Narrative with beginning, middle, end' },
  { value: 'social_media', label: 'Social Media', description: 'Short, attention-grabbing' },
];

const DURATION_OPTIONS = [
  { value: 16, label: '~16 seconds', scenes: 2 },
  { value: 24, label: '~24 seconds', scenes: 3 },
  { value: 32, label: '~32 seconds', scenes: 4 },
  { value: 48, label: '~48 seconds', scenes: 6 },
];

export default function VideoBuilder({ token, showNotification }: VideoBuilderProps) {
  const [topic, setTopic] = useState('');
  const [style, setStyle] = useState('educational');
  const [duration, setDuration] = useState(24);
  const [additionalPrompt, setAdditionalPrompt] = useState('');

  const [phase, setPhase] = useState<GenerationPhase>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const [scriptTitle, setScriptTitle] = useState('');
  const [scriptSummary, setScriptSummary] = useState('');
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [currentScene, setCurrentScene] = useState(0);
  const [totalScenes, setTotalScenes] = useState(0);

  const [videoBase64, setVideoBase64] = useState<string | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);

  const [jobHistory, setJobHistory] = useState<VideoJob[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Helper to stop polling
  const stopPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  // Resume an in-progress job by polling its status
  const resumeJob = useCallback(async (activeJobId: number) => {
    if (!token) return;

    setPhase('generating');
    setStatusMessage('Reconnecting to job...');
    setJobId(activeJobId);

    const pollJob = async () => {
      try {
        const response = await fetch(`/api/video/jobs/${activeJobId}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
          stopPolling();
          setPhase('error');
          setStatusMessage('Job not found');
          return;
        }

        const job = await response.json();

        // Update title if available
        if (job.title) setScriptTitle(job.title);

        // Update scenes from job data
        if (job.scenes && job.scenes.length > 0) {
          setTotalScenes(job.scenes.length);
          // Validate and map scene statuses - ensure they match expected values
          const validStatuses = ['pending', 'generating_image', 'generating_video', 'complete', 'error'];
          setScenes(job.scenes.map((s: { scene_number: number; status: string; narration?: string }) => ({
            scene_number: s.scene_number,
            narration: s.narration || '',
            status: (validStatuses.includes(s.status) ? s.status : 'pending') as Scene['status']
          })));

          // Find current scene (first non-complete scene)
          const currentIdx = job.scenes.findIndex((s: { status: string }) =>
            s.status !== 'complete' && s.status !== 'error'
          );
          // Use last scene number if all scenes are done, not array length
          setCurrentScene(currentIdx >= 0
            ? job.scenes[currentIdx].scene_number
            : job.scenes[job.scenes.length - 1].scene_number);
        }

        // Handle terminal states
        if (job.status === 'complete' || job.status === 'partial') {
          stopPolling();
          setPhase('complete');
          setStatusMessage(job.status === 'partial' ? 'Video generated (some scenes failed)' : 'Video generation complete!');
          if (job.final_video_base64) {
            setVideoBase64(job.final_video_base64);
          }
          showNotification('success', 'Video ready!');
        } else if (job.status === 'error') {
          stopPolling();
          setPhase('error');
          setStatusMessage(job.error_message || 'Generation failed');
          showNotification('error', job.error_message || 'Generation failed');
        } else if (job.status === 'stitching') {
          setPhase('stitching');
          setStatusMessage('Combining video segments...');
        } else if (job.status === 'planning') {
          setPhase('planning');
          setStatusMessage('Planning video script...');
        } else {
          // Still generating - update status
          setPhase('generating');
          const completedScenes = job.scenes?.filter((s: { status: string }) => s.status === 'complete').length || 0;
          setStatusMessage(`Generating scenes... (${completedScenes}/${job.scenes?.length || 0} complete)`);
        }
      } catch (error) {
        console.error('Failed to poll job:', error);
      }
    };

    // Initial poll
    await pollJob();

    // Continue polling if not in terminal state
    if (phase !== 'complete' && phase !== 'error') {
      pollIntervalRef.current = setInterval(pollJob, 5000);
    }
  }, [token, showNotification, phase]);

  // Check for in-progress job from database on mount
  useEffect(() => {
    const checkForActiveJob = async () => {
      if (!token) return;

      try {
        const response = await fetch('/api/video/jobs', {
          headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) return;

        const { jobs } = await response.json();

        // Find first in-progress job that was updated recently (within 30 min)
        const thirtyMinutesAgo = Date.now() / 1000 - 30 * 60;
        const activeJob = jobs.find((j: VideoJob) =>
          ['pending', 'planning', 'generating', 'stitching'].includes(j.status) &&
          j.updated_at > thirtyMinutesAgo
        );

        if (activeJob) {
          resumeJob(activeJob.id);
        }
      } catch (error) {
        console.error('Failed to check for active job:', error);
      }
    };

    checkForActiveJob();

    // Cleanup on unmount
    return () => stopPolling();
  }, [token, resumeJob]);

  const loadJobHistory = useCallback(async () => {
    if (!token) return;

    setIsLoadingHistory(true);
    try {
      const response = await fetch('/api/video/jobs', {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setJobHistory(data.jobs || []);
      }
    } catch (error) {
      console.error('Failed to load job history:', error);
    } finally {
      setIsLoadingHistory(false);
    }
  }, [token]);

  useEffect(() => {
    if (token && showHistory) {
      loadJobHistory();
    }
  }, [token, showHistory, loadJobHistory]);

  const handleGenerate = async () => {
    if (!token || !topic.trim()) {
      showNotification('error', 'Please enter a topic');
      return;
    }

    // Reset state
    setPhase('planning');
    setStatusMessage('Initializing...');
    setScriptTitle('');
    setScriptSummary('');
    setScenes([]);
    setCurrentScene(0);
    setTotalScenes(0);
    setVideoBase64(null);
    setJobId(null);

    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch('/api/video/generate-stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          topic,
          style,
          target_duration: duration,
          user_prompt: additionalPrompt || null
        }),
        signal: abortControllerRef.current.signal
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to start video generation');
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') continue;

            try {
              const event = JSON.parse(data);
              handleEvent(event);
            } catch (e) {
              console.error('Failed to parse event:', e);
            }
          }
        }
      }
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        setPhase('idle');
        setStatusMessage('Cancelled');
      } else {
        setPhase('error');
        setStatusMessage((error as Error).message);
        showNotification('error', (error as Error).message);
      }
    }
  };

  const handleEvent = (event: Record<string, unknown>) => {
    const type = event.type as string;

    switch (type) {
      case 'job_created':
        setJobId(event.job_id as number);
        break;

      case 'planning':
        setPhase('planning');
        setStatusMessage(event.message as string || 'Planning video script...');
        break;

      case 'script_ready':
        setScriptTitle(event.title as string || '');
        setScriptSummary(event.summary as string || '');
        setTotalScenes(event.scene_count as number || 0);
        setScenes(
          Array.from({ length: event.scene_count as number || 0 }, (_, i) => ({
            scene_number: i + 1,
            narration: '',
            status: 'pending' as const
          }))
        );
        setPhase('generating');
        setStatusMessage('Generating scenes...');
        break;

      case 'scene_image':
        setCurrentScene(event.scene as number || 0);
        setStatusMessage(`Generating image for scene ${event.scene}/${event.total}...`);
        setScenes(prev => prev.map(s =>
          s.scene_number === event.scene ? { ...s, status: 'generating_image' } : s
        ));
        break;

      case 'scene_video':
        setStatusMessage(`Generating video for scene ${event.scene}/${event.total}...`);
        setScenes(prev => prev.map(s =>
          s.scene_number === event.scene ? { ...s, status: 'generating_video' } : s
        ));
        break;

      case 'scene_complete':
        setScenes(prev => prev.map(s =>
          s.scene_number === event.scene ? { ...s, status: 'complete' } : s
        ));
        break;

      case 'scene_error':
        setScenes(prev => prev.map(s =>
          s.scene_number === event.scene ? { ...s, status: 'error' } : s
        ));
        break;

      case 'stitching':
        setPhase('stitching');
        setStatusMessage(event.message as string || 'Combining video segments...');
        break;

      case 'complete':
        setPhase('complete');
        setStatusMessage(event.partial ? 'Video generated (some scenes failed)' : 'Video generation complete!');
        setVideoBase64(event.video_base64 as string);
        showNotification('success', 'Video generated successfully!');
        break;

      case 'warning':
        showNotification('info', event.message as string || 'Warning');
        break;

      case 'error':
        setPhase('error');
        setStatusMessage(event.message as string || 'An error occurred');
        showNotification('error', event.message as string || 'Generation failed');
        break;

      case 'scene_delay':
        setStatusMessage(event.message as string || `Waiting before scene ${event.scene}...`);
        break;

      case 'scene_progress':
        setStatusMessage(event.message as string || `Rendering scene ${event.scene}...`);
        break;

      case 'quota_retry':
        setStatusMessage(event.message as string || `Quota exceeded - retrying...`);
        showNotification('info', `Retry ${event.retry}/${event.max_retries} - waiting for quota reset`);
        break;
    }
  };

  const handleCancel = () => {
    stopPolling();
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const handleDismissJob = async () => {
    if (!token || !jobId) return;

    try {
      const response = await fetch(`/api/video/jobs/${jobId}/cancel`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        stopPolling();
        setPhase('idle');
        setStatusMessage('');
        setJobId(null);
        setScenes([]);
        setScriptTitle('');
        setScriptSummary('');
        showNotification('info', 'Job dismissed');
      }
    } catch (error) {
      console.error('Failed to dismiss job:', error);
    }
  };

  const handleDownload = () => {
    if (!videoBase64) return;

    const link = document.createElement('a');
    link.href = `data:video/mp4;base64,${videoBase64}`;
    link.download = `${scriptTitle || 'video'}.mp4`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleLoadJob = async (job: VideoJob) => {
    if (!token || job.status !== 'complete') return;

    try {
      const response = await fetch(`/api/video/jobs/${job.id}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.final_video_base64) {
          setVideoBase64(data.final_video_base64);
          setScriptTitle(data.title || '');
          setPhase('complete');
          setStatusMessage('Loaded from history');
          setShowHistory(false);
        }
      }
    } catch (error) {
      showNotification('error', 'Failed to load video');
    }
  };

  const isGenerating = phase !== 'idle' && phase !== 'complete' && phase !== 'error';

  return (
    <div className="bg-gray-900/50 backdrop-blur-sm rounded-xl border border-gray-800 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
            <Video className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">Video Builder</h2>
            <p className="text-sm text-gray-400">Generate multi-scene videos with AI</p>
          </div>
        </div>
        <button
          onClick={() => setShowHistory(!showHistory)}
          className={`p-2 rounded-lg transition-colors ${
            showHistory ? 'bg-purple-500/20 text-purple-400' : 'text-gray-400 hover:text-white hover:bg-gray-800'
          }`}
          title="Job History"
        >
          <History className="w-5 h-5" />
        </button>
      </div>

      {/* History Panel */}
      {showHistory && (
        <div className="mb-6 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium text-white">Recent Videos</h3>
            <button
              onClick={loadJobHistory}
              disabled={isLoadingHistory}
              className="text-sm text-purple-400 hover:text-purple-300"
            >
              {isLoadingHistory ? 'Loading...' : 'Refresh'}
            </button>
          </div>
          {jobHistory.length === 0 ? (
            <p className="text-sm text-gray-500">No videos generated yet</p>
          ) : (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {jobHistory.map(job => (
                <button
                  key={job.id}
                  onClick={() => handleLoadJob(job)}
                  disabled={job.status !== 'complete'}
                  className={`w-full p-3 rounded-lg text-left transition-colors ${
                    job.status === 'complete'
                      ? 'bg-gray-700/50 hover:bg-gray-700'
                      : 'bg-gray-800/50 cursor-not-allowed'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white truncate">{job.title || 'Untitled'}</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      job.status === 'complete' ? 'bg-green-500/20 text-green-400' :
                      job.status === 'error' ? 'bg-red-500/20 text-red-400' :
                      'bg-yellow-500/20 text-yellow-400'
                    }`}>
                      {job.status}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {new Date(job.created_at * 1000).toLocaleString()}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Input Form */}
      <div className="space-y-4">
        {/* Topic */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Topic</label>
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g., How Kubernetes orchestrates containers"
            disabled={isGenerating}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent disabled:opacity-50"
          />
        </div>

        {/* Style & Duration */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Style</label>
            <div className="grid grid-cols-3 gap-2">
              {STYLE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setStyle(opt.value)}
                  disabled={isGenerating}
                  className={`p-2 rounded-lg border text-center transition-all ${
                    style === opt.value
                      ? 'border-purple-500 bg-purple-500/20 text-white'
                      : 'border-gray-700 bg-gray-800/50 text-gray-300 hover:border-gray-600'
                  } disabled:opacity-50`}
                >
                  <div className="font-medium text-sm">{opt.label}</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Duration</label>
            <div className="grid grid-cols-2 gap-2">
              {DURATION_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setDuration(opt.value)}
                  disabled={isGenerating}
                  className={`p-2 rounded-lg border text-center transition-all ${
                    duration === opt.value
                      ? 'border-purple-500 bg-purple-500/20 text-white'
                      : 'border-gray-700 bg-gray-800/50 text-gray-300 hover:border-gray-600'
                  } disabled:opacity-50`}
                >
                  <div className="font-medium text-sm">{opt.label}</div>
                  <div className="text-xs text-gray-500">{opt.scenes} scenes</div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Additional Prompt */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">Additional Context (optional)</label>
          <textarea
            value={additionalPrompt}
            onChange={(e) => setAdditionalPrompt(e.target.value)}
            placeholder="Any specific requirements, tone, or details..."
            rows={2}
            disabled={isGenerating}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none disabled:opacity-50"
          />
        </div>

        {/* Generate Button */}
        <div className="flex gap-3">
          <button
            onClick={handleGenerate}
            disabled={isGenerating || !topic.trim()}
            className="flex-1 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 disabled:from-gray-700 disabled:to-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-all flex items-center justify-center gap-2"
          >
            {isGenerating ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="w-5 h-5" />
                Generate Video
              </>
            )}
          </button>
          {isGenerating && (
            <button
              onClick={handleCancel}
              className="px-4 py-3 bg-red-600/20 hover:bg-red-600/30 text-red-400 font-medium rounded-lg transition-colors"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Progress Section */}
      {phase !== 'idle' && (
        <div className="mt-6 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
          {/* Phase Indicator */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              {phase === 'planning' && <Loader2 className="w-5 h-5 text-purple-400 animate-spin" />}
              {phase === 'generating' && <Film className="w-5 h-5 text-purple-400" />}
              {phase === 'stitching' && <Scissors className="w-5 h-5 text-purple-400 animate-pulse" />}
              {phase === 'complete' && <Check className="w-5 h-5 text-green-400" />}
              {phase === 'error' && <AlertCircle className="w-5 h-5 text-red-400" />}
              <span className={`font-medium ${
                phase === 'complete' ? 'text-green-400' :
                phase === 'error' ? 'text-red-400' :
                'text-white'
              }`}>
                {statusMessage}
              </span>
            </div>
            {isGenerating && jobId && (
              <button
                onClick={handleDismissJob}
                className="text-sm text-gray-400 hover:text-red-400 transition-colors"
                title="Dismiss this job"
              >
                Dismiss
              </button>
            )}
          </div>

          {/* Script Info */}
          {scriptTitle && (
            <div className="mb-4 p-3 bg-gray-900/50 rounded-lg">
              <h4 className="font-medium text-white">{scriptTitle}</h4>
              {scriptSummary && <p className="text-sm text-gray-400 mt-1">{scriptSummary}</p>}
            </div>
          )}

          {/* Scene Progress */}
          {scenes.length > 0 && (
            <div className="mb-4">
              <div className="flex items-center justify-between text-sm text-gray-400 mb-2">
                <span>Scenes</span>
                <span>{scenes.filter(s => s.status === 'complete').length} / {scenes.length}</span>
              </div>
              <div className="flex gap-1">
                {scenes.map((scene) => (
                  <div
                    key={scene.scene_number}
                    className={`flex-1 h-2 rounded-full transition-colors ${
                      scene.status === 'complete' ? 'bg-green-500' :
                      scene.status === 'generating_image' ? 'bg-purple-500 animate-pulse' :
                      scene.status === 'generating_video' ? 'bg-pink-500 animate-pulse' :
                      scene.status === 'error' ? 'bg-red-500' :
                      'bg-gray-700'
                    }`}
                    title={`Scene ${scene.scene_number}: ${scene.status}`}
                  />
                ))}
              </div>
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-purple-500" /> Image
                </span>
                <span className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-pink-500" /> Video
                </span>
                <span className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-green-500" /> Done
                </span>
              </div>
            </div>
          )}

          {/* Video Preview */}
          {videoBase64 && (
            <div className="mt-4">
              <video
                src={`data:video/mp4;base64,${videoBase64}`}
                controls
                className="w-full rounded-lg"
              />
              <button
                onClick={handleDownload}
                className="mt-3 w-full py-2.5 bg-green-600 hover:bg-green-500 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                <Download className="w-4 h-4" />
                Download Video
              </button>
            </div>
          )}
        </div>
      )}

      {/* Info Box */}
      <div className="mt-6 p-4 bg-purple-500/10 border border-purple-500/30 rounded-lg">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-purple-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-gray-300">
            <p className="font-medium text-purple-300 mb-1">About Video Generation</p>
            <p>
              Videos are generated using Veo 3.1 with 8-second scenes. Each scene includes a first-frame image
              for visual consistency. Set up your author bio in the Bio tab for character reference.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
