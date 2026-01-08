'use client';

import { useState, useRef } from 'react';
import { Upload, Loader2, FileVideo, Check, AlertCircle, Twitter, Linkedin, Youtube, Copy, FileText } from 'lucide-react';
import { fetchWithRetry } from '@/utils/fetchWithRetry';

interface VideoPostBoxProps {
  token: string | null;
  connections: {
    twitter: boolean;
    linkedin: boolean;
    youtube: boolean;
  };
  showNotification: (type: 'success' | 'error' | 'info', message: string) => void;
}

type ProgressStep = 'idle' | 'uploading' | 'transcribing' | 'generating_posts' | 'complete' | 'error';

const ACCEPTED_TYPES = ['video/mp4', 'video/webm', 'video/quicktime', 'video/x-m4v'];
const MAX_SIZE_MB = 500;
const CHUNK_SIZE_MB = 50;

interface GeneratedContent {
  transcript: string | null;
  x_post: string | null;
  linkedin_post: string | null;
  youtube_title: string | null;
  youtube_description: string | null;
  blog_post: string | null;
  video_ref: string | null;  // Server-side reference (no more huge base64)
  mime_type: string | null;
}

export default function VideoPostBox({ token, connections, showNotification }: VideoPostBoxProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState<ProgressStep>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const [content, setContent] = useState<GeneratedContent>({
    transcript: null,
    x_post: null,
    linkedin_post: null,
    youtube_title: null,
    youtube_description: null,
    blog_post: null,
    video_ref: null,
    mime_type: null
  });
  const [isPosting, setIsPosting] = useState<{ twitter: boolean; linkedin: boolean; youtube: boolean }>({
    twitter: false,
    linkedin: false,
    youtube: false
  });
  const [posted, setPosted] = useState<{ twitter: boolean; linkedin: boolean; youtube: boolean }>({
    twitter: false,
    linkedin: false,
    youtube: false
  });
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      return `Unsupported file type: ${file.type || 'unknown'}. Use MP4, WebM, or MOV.`;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Max: ${MAX_SIZE_MB}MB`;
    }
    return null;
  };

  const handleFileSelect = (file: File) => {
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      showNotification('error', validationError);
      return;
    }
    setSelectedFile(file);
    setError(null);
    // Reset outputs
    setContent({
      transcript: null,
      x_post: null,
      linkedin_post: null,
      youtube_title: null,
      youtube_description: null,
      blog_post: null,
      video_ref: null,
      mime_type: null
    });
    setProgress('idle');
    setPosted({ twitter: false, linkedin: false, youtube: false });
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  };

  // Chunked upload for large files (>50MB)
  const uploadFileChunked = async (file: File): Promise<string> => {
    const chunkSize = CHUNK_SIZE_MB * 1024 * 1024;
    const totalChunks = Math.ceil(file.size / chunkSize);

    // Step 1: Initialize upload
    const initResponse = await fetchWithRetry('/api/upload/init', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type,
        total_size: file.size
      })
    });

    const initData = await initResponse.json();
    if (!initResponse.ok) {
      throw new Error(initData.detail || 'Failed to initialize upload');
    }

    const upload_id = initData.upload_id;
    if (!upload_id || typeof upload_id !== 'string') {
      throw new Error('Invalid upload_id received from server');
    }

    // Step 2: Upload chunks
    for (let i = 0; i < totalChunks; i++) {
      setUploadProgress({ current: i + 1, total: totalChunks });
      setStatusMessage(`Uploading chunk ${i + 1} of ${totalChunks}...`);

      const start = i * chunkSize;
      const end = Math.min(start + chunkSize, file.size);

      // Read chunk as ArrayBuffer first for better browser compatibility
      const chunkSlice = file.slice(start, end);
      const arrayBuffer = await chunkSlice.arrayBuffer();
      const chunkBlob = new Blob([arrayBuffer], { type: 'application/octet-stream' });

      const formData = new FormData();
      formData.append('chunk', chunkBlob, `chunk_${i}.bin`);
      formData.append('index', String(i));

      const chunkUrl = `/api/upload/chunk/${encodeURIComponent(upload_id)}`;
      const chunkResponse = await fetchWithRetry(chunkUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (!chunkResponse.ok) {
        const data = await chunkResponse.json();
        throw new Error(data.detail || `Failed to upload chunk ${i + 1}`);
      }
    }

    // Step 3: Complete upload
    setStatusMessage('Finalizing upload...');
    const completeResponse = await fetchWithRetry(`/api/upload/complete/${upload_id}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!completeResponse.ok) {
      const data = await completeResponse.json();
      throw new Error(data.detail || 'Failed to complete upload');
    }

    setUploadProgress(null);
    return upload_id;
  };

  const handleGenerate = async () => {
    if (!selectedFile || !token) return;

    setIsProcessing(true);
    setError(null);
    setProgress('uploading');
    setStatusMessage('Uploading video...');
    setUploadProgress(null);
    setContent({
      transcript: null,
      x_post: null,
      linkedin_post: null,
      youtube_title: null,
      youtube_description: null,
      blog_post: null,
      video_ref: null,
      mime_type: null
    });
    setPosted({ twitter: false, linkedin: false, youtube: false });

    try {
      let response: Response;
      const chunkThreshold = CHUNK_SIZE_MB * 1024 * 1024; // Use chunked upload for files > 50MB

      if (selectedFile.size > chunkThreshold) {
        // Use chunked upload for large files
        const uploadId = await uploadFileChunked(selectedFile);

        // Now process with upload_id
        setStatusMessage('Processing video...');
        const formData = new FormData();
        formData.append('upload_id', uploadId);

        response = await fetchWithRetry('/api/generate-video-post-stream', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          },
          body: formData
        });
      } else {
        // Direct upload for small files
        const formData = new FormData();
        formData.append('file', selectedFile);

        response = await fetchWithRetry('/api/generate-video-post-stream', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          },
          body: formData
        });
      }

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to process video');
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('Failed to read response stream');
      }

      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const event of events) {
          const lines = event.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6);
              if (dataStr === '[DONE]') continue;

              try {
                const data = JSON.parse(dataStr);

                switch (data.type) {
                  case 'progress':
                    setProgress(data.step as ProgressStep);
                    setStatusMessage(data.message || '');
                    break;
                  case 'transcript':
                    setContent(prev => ({ ...prev, transcript: data.transcript }));
                    break;
                  case 'x_post':
                    setContent(prev => ({ ...prev, x_post: data.x_post }));
                    break;
                  case 'linkedin_post':
                    setContent(prev => ({ ...prev, linkedin_post: data.linkedin_post }));
                    break;
                  case 'youtube':
                    setContent(prev => ({
                      ...prev,
                      youtube_title: data.title,
                      youtube_description: data.description
                    }));
                    break;
                  case 'blog_post':
                    setContent(prev => ({ ...prev, blog_post: data.blog_post }));
                    break;
                  case 'video_ready':
                    setContent(prev => ({
                      ...prev,
                      video_ref: data.video_ref,
                      mime_type: data.mime_type
                    }));
                    break;
                  case 'complete':
                    setProgress('complete');
                    setStatusMessage('');
                    showNotification('success', 'Posts generated! Review and post to your platforms.');
                    break;
                  case 'error':
                    throw new Error(data.message);
                }
              } catch (parseErr) {
                // Ignore JSON parse errors for partial chunks
              }
            }
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to process video';
      setError(message);
      setProgress('error');
      showNotification('error', message);
    } finally {
      setIsProcessing(false);
      setStatusMessage('');
    }
  };

  const handlePost = async (platform: 'twitter' | 'linkedin' | 'youtube') => {
    if (!token || !content.video_ref) return;

    setIsPosting(prev => ({ ...prev, [platform]: true }));

    try {
      const response = await fetchWithRetry('/api/post-video', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          video_ref: content.video_ref,
          x_post: content.x_post,
          linkedin_post: content.linkedin_post,
          youtube_title: content.youtube_title,
          youtube_description: content.youtube_description,
          platforms: [platform]
        })
      });

      const data = await response.json();

      if (data.posted?.includes(platform)) {
        setPosted(prev => ({ ...prev, [platform]: true }));
        const platformName = platform === 'twitter' ? 'X/Twitter' : platform === 'linkedin' ? 'LinkedIn' : 'YouTube';
        showNotification('success', `Posted to ${platformName}!`);
      } else if (data.errors?.[platform]) {
        throw new Error(data.errors[platform]);
      } else {
        throw new Error('Failed to post');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to post';
      showNotification('error', message);
    } finally {
      setIsPosting(prev => ({ ...prev, [platform]: false }));
    }
  };

  const handleCopy = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showNotification('success', `${label} copied to clipboard`);
    } catch {
      showNotification('error', 'Failed to copy');
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setContent({
      transcript: null,
      x_post: null,
      linkedin_post: null,
      youtube_title: null,
      youtube_description: null,
      blog_post: null,
      video_ref: null,
      mime_type: null
    });
    setProgress('idle');
    setError(null);
    setStatusMessage('');
    setUploadProgress(null);
    setPosted({ twitter: false, linkedin: false, youtube: false });
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const hasContent = content.x_post || content.linkedin_post || content.youtube_title;

  const progressSteps = [
    { key: 'uploading', label: 'Upload' },
    { key: 'transcribing', label: 'Transcribe' },
    { key: 'generating_posts', label: 'Generate' },
  ];

  const getStepStatus = (stepKey: string) => {
    const stepOrder = ['uploading', 'transcribing', 'generating_posts', 'complete'];
    const currentIndex = stepOrder.indexOf(progress);
    const stepIndex = stepOrder.indexOf(stepKey);
    if (currentIndex > stepIndex) return 'complete';
    if (currentIndex === stepIndex) return 'active';
    return 'pending';
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Left Panel: Video Upload */}
      <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-4 space-y-4">
        <h3 className="text-xl font-semibold text-white flex items-center gap-2">
          <Upload className="w-6 h-6 text-purple-500" />
          Upload Video
        </h3>

        <p className="text-gray-400 text-sm">
          Upload a video to generate promotional posts for X, LinkedIn, and YouTube.
        </p>

        {/* Drop Zone */}
        <div
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
            isDragging
              ? 'border-purple-500 bg-purple-500/10'
              : selectedFile
              ? 'border-green-500/50 bg-green-500/5'
              : 'border-gray-700 hover:border-gray-600 hover:bg-gray-800/30'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES.join(',')}
            onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
            className="hidden"
            disabled={isProcessing}
          />

          {selectedFile ? (
            <div className="space-y-2">
              <FileVideo className="w-12 h-12 mx-auto text-green-400" />
              <p className="text-white font-medium">{selectedFile.name}</p>
              <p className="text-gray-400 text-sm">
                {(selectedFile.size / (1024 * 1024)).toFixed(1)} MB
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <Upload className="w-12 h-12 mx-auto text-gray-500" />
              <p className="text-gray-300">Drop video here or click to browse</p>
              <p className="text-gray-500 text-sm">MP4, WebM, MOV. Max {MAX_SIZE_MB}MB</p>
            </div>
          )}
        </div>

        {error && (
          <div className="p-3 bg-red-900/20 border border-red-700/30 rounded-lg flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={handleGenerate}
            disabled={isProcessing || !selectedFile}
            className="flex-1 py-3 px-4 rounded-lg font-medium transition-all bg-gradient-to-r from-purple-600 to-pink-600 hover:opacity-90 text-white neon-glow disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isProcessing ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                {statusMessage || 'Processing...'}
              </>
            ) : (
              <>
                <Upload className="w-5 h-5" />
                Generate Posts
              </>
            )}
          </button>

          {(selectedFile || hasContent) && (
            <button
              onClick={handleReset}
              disabled={isProcessing}
              className="py-3 px-4 rounded-lg font-medium transition-all bg-gray-700 hover:bg-gray-600 text-white disabled:opacity-50"
            >
              Clear
            </button>
          )}
        </div>

        {/* Progress Steps */}
        {isProcessing && (
          <div className="p-3 bg-purple-900/20 border border-purple-700/30 rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              {progressSteps.map((step, index) => {
                const status = getStepStatus(step.key);
                return (
                  <div key={step.key} className="flex items-center">
                    <div className="flex flex-col items-center">
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium ${
                          status === 'complete'
                            ? 'bg-green-500 text-white'
                            : status === 'active'
                            ? 'bg-purple-500 text-white animate-pulse'
                            : 'bg-gray-700 text-gray-400'
                        }`}
                      >
                        {status === 'complete' ? <Check className="w-4 h-4" /> : index + 1}
                      </div>
                      <span className={`text-xs mt-1 ${status === 'active' ? 'text-purple-300' : 'text-gray-500'}`}>
                        {step.label}
                      </span>
                    </div>
                    {index < progressSteps.length - 1 && (
                      <div className={`w-12 h-0.5 mx-2 ${status === 'complete' ? 'bg-green-500' : 'bg-gray-700'}`} />
                    )}
                  </div>
                );
              })}
            </div>

            {/* Chunked Upload Progress Bar */}
            {uploadProgress && (
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-gray-400">
                  <span>Uploading large file...</span>
                  <span>{Math.round((uploadProgress.current / uploadProgress.total) * 100)}%</span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${(uploadProgress.current / uploadProgress.total) * 100}%` }}
                  />
                </div>
                <p className="text-xs text-gray-500 text-center">
                  Chunk {uploadProgress.current} of {uploadProgress.total} ({CHUNK_SIZE_MB}MB each)
                </p>
              </div>
            )}
          </div>
        )}

        {/* Connection Warning */}
        {!connections.twitter && !connections.linkedin && !connections.youtube && (
          <div className="p-3 bg-yellow-900/20 border border-yellow-700/30 rounded-lg">
            <p className="text-sm text-yellow-400">
              Connect at least one platform in the Campaign tab to post.
            </p>
          </div>
        )}
      </div>

      {/* Right Panel: Preview */}
      <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-4 space-y-4 h-[700px] overflow-y-auto">
        <h3 className="text-xl font-semibold text-white flex items-center gap-2">
          <FileVideo className="w-6 h-6 text-purple-500" />
          Preview
        </h3>

        {!hasContent && !isProcessing && (
          <div className="text-center text-gray-500 py-8">
            <FileVideo className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p className="text-sm">Posts will appear here after processing.</p>
          </div>
        )}

        {/* X/Twitter Post Card */}
        {(content.x_post || (isProcessing && progress === 'generating_posts')) && (
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Twitter className="w-5 h-5 text-blue-400" />
                <span className="text-white font-medium">X / Twitter</span>
              </div>
              {content.x_post && (
                <div className="flex items-center gap-2">
                  <span className={`text-xs ${content.x_post.length > 280 ? 'text-red-400' : 'text-gray-400'}`}>
                    {content.x_post.length}/280
                  </span>
                  <button onClick={() => handleCopy(content.x_post!, 'Tweet')} className="text-gray-400 hover:text-white">
                    <Copy className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>

            {content.x_post ? (
              <>
                <p className="text-gray-200 text-sm whitespace-pre-wrap mb-3">{content.x_post}</p>
                <button
                  onClick={() => handlePost('twitter')}
                  disabled={!connections.twitter || isPosting.twitter || posted.twitter || !content.video_ref}
                  className={`w-full py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    posted.twitter
                      ? 'bg-green-600 text-white cursor-default'
                      : connections.twitter && content.video_ref
                      ? 'bg-blue-600 hover:bg-blue-700 text-white'
                      : 'bg-gray-700 text-gray-400 cursor-not-allowed'
                  }`}
                >
                  {isPosting.twitter ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : posted.twitter ? (
                    <><Check className="w-4 h-4" /> Posted!</>
                  ) : !connections.twitter ? (
                    <><AlertCircle className="w-4 h-4" /> Connect X first</>
                  ) : (
                    <><Twitter className="w-4 h-4" /> Post to X</>
                  )}
                </button>
              </>
            ) : (
              <div className="flex items-center gap-2 text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Generating...</span>
              </div>
            )}
          </div>
        )}

        {/* LinkedIn Post Card */}
        {(content.linkedin_post || (isProcessing && progress === 'generating_posts')) && (
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Linkedin className="w-5 h-5 text-blue-500" />
                <span className="text-white font-medium">LinkedIn</span>
              </div>
              {content.linkedin_post && (
                <button onClick={() => handleCopy(content.linkedin_post!, 'LinkedIn post')} className="text-gray-400 hover:text-white">
                  <Copy className="w-4 h-4" />
                </button>
              )}
            </div>

            {content.linkedin_post ? (
              <>
                <p className="text-gray-200 text-sm whitespace-pre-wrap mb-3 max-h-32 overflow-y-auto">
                  {content.linkedin_post}
                </p>
                <button
                  onClick={() => handlePost('linkedin')}
                  disabled={!connections.linkedin || isPosting.linkedin || posted.linkedin || !content.video_ref}
                  className={`w-full py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    posted.linkedin
                      ? 'bg-green-600 text-white cursor-default'
                      : connections.linkedin && content.video_ref
                      ? 'bg-blue-700 hover:bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-400 cursor-not-allowed'
                  }`}
                >
                  {isPosting.linkedin ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : posted.linkedin ? (
                    <><Check className="w-4 h-4" /> Posted!</>
                  ) : !connections.linkedin ? (
                    <><AlertCircle className="w-4 h-4" /> Connect LinkedIn first</>
                  ) : (
                    <><Linkedin className="w-4 h-4" /> Post to LinkedIn</>
                  )}
                </button>
              </>
            ) : (
              <div className="flex items-center gap-2 text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Generating...</span>
              </div>
            )}
          </div>
        )}

        {/* YouTube Card */}
        {(content.youtube_title || (isProcessing && progress === 'generating_posts')) && (
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Youtube className="w-5 h-5 text-red-500" />
                <span className="text-white font-medium">YouTube</span>
              </div>
              {content.youtube_title && (
                <button
                  onClick={() => handleCopy(`${content.youtube_title}\n\n${content.youtube_description}`, 'YouTube content')}
                  className="text-gray-400 hover:text-white"
                >
                  <Copy className="w-4 h-4" />
                </button>
              )}
            </div>

            {content.youtube_title ? (
              <>
                <div className="mb-2">
                  <p className="text-xs text-gray-500 mb-1">Title</p>
                  <p className="text-white font-medium text-sm">{content.youtube_title}</p>
                </div>
                <div className="mb-3">
                  <p className="text-xs text-gray-500 mb-1">Description</p>
                  <p className="text-gray-200 text-sm whitespace-pre-wrap max-h-24 overflow-y-auto">
                    {content.youtube_description}
                  </p>
                </div>
                <button
                  onClick={() => handlePost('youtube')}
                  disabled={!connections.youtube || isPosting.youtube || posted.youtube || !content.video_ref}
                  className={`w-full py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    posted.youtube
                      ? 'bg-green-600 text-white cursor-default'
                      : connections.youtube && content.video_ref
                      ? 'bg-red-600 hover:bg-red-700 text-white'
                      : 'bg-gray-700 text-gray-400 cursor-not-allowed'
                  }`}
                >
                  {isPosting.youtube ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : posted.youtube ? (
                    <><Check className="w-4 h-4" /> Uploaded!</>
                  ) : !connections.youtube ? (
                    <><AlertCircle className="w-4 h-4" /> Connect YouTube first</>
                  ) : (
                    <><Youtube className="w-4 h-4" /> Upload to YouTube</>
                  )}
                </button>
              </>
            ) : (
              <div className="flex items-center gap-2 text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Generating...</span>
              </div>
            )}
          </div>
        )}

        {/* Blog Post Preview (collapsible) */}
        {content.blog_post && (
          <details className="bg-gray-800/50 border border-gray-700 rounded-lg" open>
            <summary className="p-4 cursor-pointer text-white font-medium flex items-center gap-2">
              <FileText className="w-5 h-5 text-green-400" />
              Blog Post
              <span className="text-xs text-gray-500 ml-auto">
                {content.blog_post.split(/\s+/).length} words
              </span>
            </summary>
            <div className="px-4 pb-4">
              <div className="text-gray-300 text-sm whitespace-pre-wrap max-h-64 overflow-y-auto prose prose-invert prose-sm">
                {content.blog_post}
              </div>
              <button
                onClick={() => handleCopy(content.blog_post!, 'Blog post')}
                className="mt-3 text-sm text-green-400 hover:text-green-300 flex items-center gap-1"
              >
                <Copy className="w-3 h-3" />
                Copy blog post (markdown)
              </button>
            </div>
          </details>
        )}

        {/* Transcript Preview (collapsible) */}
        {content.transcript && (
          <details className="bg-gray-800/50 border border-gray-700 rounded-lg">
            <summary className="p-4 cursor-pointer text-white font-medium flex items-center gap-2">
              <FileVideo className="w-5 h-5 text-purple-400" />
              Transcript
            </summary>
            <div className="px-4 pb-4">
              <p className="text-gray-300 text-sm whitespace-pre-wrap max-h-48 overflow-y-auto">
                {content.transcript}
              </p>
              <button
                onClick={() => handleCopy(content.transcript!, 'Transcript')}
                className="mt-2 text-sm text-purple-400 hover:text-purple-300 flex items-center gap-1"
              >
                <Copy className="w-3 h-3" />
                Copy transcript
              </button>
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
