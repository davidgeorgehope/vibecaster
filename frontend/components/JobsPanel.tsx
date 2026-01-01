'use client';

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Download, X, ChevronDown, ChevronRight, AlertCircle, CheckCircle, Clock, Loader2, ListTodo } from 'lucide-react';

interface VideoScene {
  id: number;
  scene_number: number;
  status: 'pending' | 'generating' | 'complete' | 'error';
  prompt?: string;
  narration?: string;
  error_message?: string;
}

interface VideoJob {
  id: number;
  job_id: string;
  status: 'pending' | 'planning' | 'generating' | 'complete' | 'partial' | 'error';
  title: string;
  created_at: number;
  updated_at: number;
  error_message?: string;
  scenes?: VideoScene[];
  has_final_video?: boolean;
}

type FilterStatus = 'all' | 'in_progress' | 'completed' | 'failed';

interface JobsPanelProps {
  token: string | null;
  showNotification: (type: 'success' | 'error' | 'info', message: string) => void;
}

export default function JobsPanel({ token, showNotification }: JobsPanelProps) {
  const [jobs, setJobs] = useState<VideoJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterStatus>('all');
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);
  const [expandedJobDetails, setExpandedJobDetails] = useState<VideoJob | null>(null);

  const fetchJobs = useCallback(async () => {
    if (!token) return;

    try {
      const response = await fetch('/api/video/jobs', {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) throw new Error('Failed to fetch jobs');

      const data = await response.json();
      setJobs(data.jobs || []);
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
    } finally {
      setLoading(false);
    }
  }, [token]);

  const fetchJobDetails = useCallback(async (jobId: number) => {
    if (!token) return null;

    try {
      const response = await fetch(`/api/video/jobs/${jobId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) throw new Error('Failed to fetch job details');

      return await response.json();
    } catch (error) {
      console.error('Failed to fetch job details:', error);
      return null;
    }
  }, [token]);

  // Initial fetch
  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Poll for updates when there are in-progress jobs
  useEffect(() => {
    const hasInProgress = jobs.some(j =>
      ['pending', 'planning', 'generating', 'stitching'].includes(j.status)
    );

    if (!hasInProgress) return;

    const interval = setInterval(() => {
      fetchJobs();
      // Also refresh expanded job details
      if (expandedJobId) {
        fetchJobDetails(expandedJobId).then(details => {
          if (details) setExpandedJobDetails(details);
        });
      }
    }, 5000);  // Poll every 5s for faster job updates

    return () => clearInterval(interval);
  }, [jobs, fetchJobs, expandedJobId, fetchJobDetails]);

  const handleExpand = async (jobId: number) => {
    if (expandedJobId === jobId) {
      setExpandedJobId(null);
      setExpandedJobDetails(null);
    } else {
      setExpandedJobId(jobId);
      const details = await fetchJobDetails(jobId);
      setExpandedJobDetails(details);
    }
  };

  const handleCancel = async (jobId: number) => {
    if (!token) return;

    try {
      const response = await fetch(`/api/video/jobs/${jobId}/cancel`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) throw new Error('Failed to cancel job');

      showNotification('info', 'Job cancelled');
      fetchJobs();
    } catch (error) {
      showNotification('error', 'Failed to cancel job');
    }
  };

  const handleDismiss = async (jobId: number) => {
    if (!token) return;

    try {
      const response = await fetch(`/api/video/jobs/${jobId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) throw new Error('Failed to dismiss job');

      showNotification('info', 'Job dismissed');
      fetchJobs();
    } catch (error) {
      showNotification('error', 'Failed to dismiss job');
    }
  };

  const handleDownload = async (job: VideoJob) => {
    if (!token || !job.has_final_video) return;

    try {
      const response = await fetch(`/api/video/jobs/${job.id}/download`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) throw new Error('Failed to download video');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${job.title || 'video'}.mp4`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      showNotification('success', 'Video downloaded');
    } catch (error) {
      showNotification('error', 'Failed to download video');
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'complete':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'partial':
        return <AlertCircle className="w-5 h-5 text-yellow-500" />;
      case 'error':
        return <X className="w-5 h-5 text-red-500" />;
      case 'pending':
        return <Clock className="w-5 h-5 text-gray-400" />;
      default:
        return <Loader2 className="w-5 h-5 text-purple-500 animate-spin" />;
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'pending': return 'Pending';
      case 'planning': return 'Planning';
      case 'generating': return 'Generating';
      case 'stitching': return 'Stitching';
      case 'complete': return 'Complete';
      case 'partial': return 'Partial';
      case 'error': return 'Error';
      default: return status;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'complete': return 'text-green-400';
      case 'partial': return 'text-yellow-400';
      case 'error': return 'text-red-400';
      case 'pending': return 'text-gray-400';
      default: return 'text-purple-400';
    }
  };

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    return date.toLocaleDateString();
  };

  const isInProgress = (status: string) =>
    ['pending', 'planning', 'generating', 'stitching'].includes(status);

  const filteredJobs = jobs.filter(job => {
    if (filter === 'all') return true;
    if (filter === 'in_progress') return isInProgress(job.status);
    if (filter === 'completed') return job.status === 'complete' || job.status === 'partial';
    if (filter === 'failed') return job.status === 'error';
    return true;
  });

  const getSceneProgress = (job: VideoJob) => {
    if (!expandedJobDetails || expandedJobDetails.id !== job.id) return null;
    const scenes = expandedJobDetails.scenes || [];
    const completed = scenes.filter(s => s.status === 'complete').length;
    return { completed, total: scenes.length };
  };

  return (
    <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-xl p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <ListTodo className="w-6 h-6 text-purple-500" />
          <h2 className="text-xl font-semibold text-white">Video Jobs</h2>
        </div>
        <button
          onClick={() => { setLoading(true); fetchJobs(); }}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-300 hover:text-white hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Filter */}
      <div className="flex gap-2 mb-4">
        {[
          { id: 'all', label: 'All' },
          { id: 'in_progress', label: 'In Progress' },
          { id: 'completed', label: 'Completed' },
          { id: 'failed', label: 'Failed' }
        ].map(f => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id as FilterStatus)}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              filter === f.id
                ? 'bg-purple-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Job List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
        </div>
      ) : filteredJobs.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <ListTodo className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No video jobs found</p>
          <p className="text-sm mt-1">Create videos from the Video or Post Builder tabs</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredJobs.map(job => (
            <div
              key={job.id}
              className="bg-gray-800/50 border border-gray-700 rounded-lg overflow-hidden"
            >
              {/* Job Row */}
              <div
                className="flex items-center gap-4 p-4 cursor-pointer hover:bg-gray-800/70"
                onClick={() => handleExpand(job.id)}
              >
                {/* Expand Icon */}
                <div className="text-gray-500">
                  {expandedJobId === job.id ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                </div>

                {/* Status Icon */}
                {getStatusIcon(job.status)}

                {/* Title & Info */}
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-white truncate">
                    {job.title || 'Untitled Video'}
                  </div>
                  <div className="text-sm text-gray-400">
                    {formatTime(job.created_at)}
                    {job.error_message && (
                      <span className="text-red-400 ml-2">• {job.error_message}</span>
                    )}
                  </div>
                </div>

                {/* Status Label */}
                <div className={`text-sm font-medium ${getStatusColor(job.status)}`}>
                  {getStatusLabel(job.status)}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                  {(job.status === 'complete' || job.status === 'partial') && job.has_final_video && (
                    <button
                      onClick={() => handleDownload(job)}
                      className="flex items-center gap-1 px-3 py-1.5 text-sm bg-green-600 hover:bg-green-500 text-white rounded-lg transition-colors"
                    >
                      <Download className="w-4 h-4" />
                      Download
                    </button>
                  )}
                  {isInProgress(job.status) && (
                    <button
                      onClick={() => handleCancel(job.id)}
                      className="flex items-center gap-1 px-3 py-1.5 text-sm bg-red-600/20 hover:bg-red-600/40 text-red-400 rounded-lg transition-colors"
                    >
                      <X className="w-4 h-4" />
                      Cancel
                    </button>
                  )}
                  {job.status === 'error' && (
                    <button
                      onClick={() => handleDismiss(job.id)}
                      className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
                    >
                      <X className="w-4 h-4" />
                      Dismiss
                    </button>
                  )}
                </div>
              </div>

              {/* Expanded Details */}
              {expandedJobId === job.id && expandedJobDetails && (
                <div className="border-t border-gray-700 p-4 bg-gray-900/50">
                  <h4 className="text-sm font-medium text-gray-300 mb-3">Scene Progress</h4>
                  {expandedJobDetails.scenes && expandedJobDetails.scenes.length > 0 ? (
                    <div className="space-y-2">
                      {expandedJobDetails.scenes.map(scene => (
                        <div
                          key={scene.id}
                          className="flex items-center gap-3 text-sm"
                        >
                          <div className="w-6 text-center text-gray-500">
                            {scene.scene_number}
                          </div>
                          {getStatusIcon(scene.status)}
                          <div className="flex-1 text-gray-300 truncate">
                            {scene.prompt || scene.narration || 'Scene'}
                          </div>
                          <div className={`text-xs ${getStatusColor(scene.status)}`}>
                            {getStatusLabel(scene.status)}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">No scene details available</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
