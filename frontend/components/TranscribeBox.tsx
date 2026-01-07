'use client';

import { useState, useRef } from 'react';
import { Mic, Loader2, FileAudio, Check, AlertCircle, Copy, Upload } from 'lucide-react';

interface TranscribeBoxProps {
  token: string | null;
  showNotification: (type: 'success' | 'error' | 'info', message: string) => void;
}

type OutputTab = 'transcript' | 'summary' | 'blog';
type ProgressStep = 'idle' | 'uploading' | 'transcribing' | 'summarizing' | 'generating_blog' | 'complete' | 'error';

const ACCEPTED_TYPES = [
  'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav',
  'audio/aac', 'audio/ogg', 'audio/flac', 'audio/aiff',
  'video/mp4', 'video/webm', 'video/quicktime', 'video/x-m4v'
];

const MAX_SIZE_MB = 500;
const CHUNK_SIZE_MB = 50;

export default function TranscribeBox({ token, showNotification }: TranscribeBoxProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState<ProgressStep>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const [transcript, setTranscript] = useState('');
  const [summary, setSummary] = useState('');
  const [blogPost, setBlogPost] = useState('');
  const [activeTab, setActiveTab] = useState<OutputTab>('transcript');
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Chunked upload for large files (>50MB)
  const uploadFileChunked = async (file: File): Promise<string> => {
    const chunkSize = CHUNK_SIZE_MB * 1024 * 1024;
    const totalChunks = Math.ceil(file.size / chunkSize);

    // Step 1: Initialize upload
    const initResponse = await fetch('/api/upload/init', {
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

    // Step 2: Upload chunks
    for (let i = 0; i < totalChunks; i++) {
      setUploadProgress({ current: i + 1, total: totalChunks });
      setStatusMessage(`Uploading chunk ${i + 1} of ${totalChunks}...`);

      const start = i * chunkSize;
      const end = Math.min(start + chunkSize, file.size);

      const chunkSlice = file.slice(start, end);
      const arrayBuffer = await chunkSlice.arrayBuffer();
      const chunkBlob = new Blob([arrayBuffer], { type: 'application/octet-stream' });

      const formData = new FormData();
      formData.append('chunk', chunkBlob, `chunk_${i}.bin`);
      formData.append('index', String(i));

      const chunkResponse = await fetch(`/api/upload/chunk/${encodeURIComponent(upload_id)}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });

      if (!chunkResponse.ok) {
        const data = await chunkResponse.json();
        throw new Error(data.detail || `Failed to upload chunk ${i + 1}`);
      }
    }

    // Step 3: Complete upload
    setStatusMessage('Finalizing upload...');
    const completeResponse = await fetch(`/api/upload/complete/${upload_id}`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (!completeResponse.ok) {
      const data = await completeResponse.json();
      throw new Error(data.detail || 'Failed to complete upload');
    }

    setUploadProgress(null);
    return upload_id;
  };

  const validateFile = (file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      return `Unsupported file type: ${file.type || 'unknown'}. Use MP3, WAV, MP4, etc.`;
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
    // Reset outputs when new file selected
    setTranscript('');
    setSummary('');
    setBlogPost('');
    setProgress('idle');
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleGenerate = async () => {
    if (!selectedFile || !token) return;

    setIsProcessing(true);
    setError(null);
    setTranscript('');
    setSummary('');
    setBlogPost('');
    setProgress('uploading');
    setStatusMessage('Uploading file...');
    setUploadProgress(null);

    try {
      let response: Response;
      const chunkThreshold = CHUNK_SIZE_MB * 1024 * 1024;

      if (selectedFile.size > chunkThreshold) {
        // Use chunked upload for large files
        const uploadId = await uploadFileChunked(selectedFile);

        setStatusMessage('Processing file...');
        const formData = new FormData();
        formData.append('upload_id', uploadId);

        response = await fetch('/api/transcribe-stream', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: formData
        });
      } else {
        // Direct upload for small files
        const formData = new FormData();
        formData.append('file', selectedFile);

        response = await fetch('/api/transcribe-stream', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: formData
        });
      }

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to process file');
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

                if (data.message) {
                  setStatusMessage(data.message);
                }

                switch (data.type) {
                  case 'progress':
                    setProgress(data.step as ProgressStep);
                    break;
                  case 'transcript':
                    setTranscript(data.transcript);
                    setActiveTab('transcript');
                    break;
                  case 'summary':
                    setSummary(data.summary);
                    break;
                  case 'blog_post':
                    setBlogPost(data.blog_post);
                    break;
                  case 'complete':
                    setProgress('complete');
                    setStatusMessage('');
                    showNotification('success', 'Transcription complete!');
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
      const message = err instanceof Error ? err.message : 'Failed to process file';
      setError(message);
      setProgress('error');
      showNotification('error', message);
    } finally {
      setIsProcessing(false);
      setStatusMessage('');
    }
  };

  const handleCopy = async (content: string, label: string) => {
    try {
      await navigator.clipboard.writeText(content);
      showNotification('success', `${label} copied to clipboard`);
    } catch {
      showNotification('error', 'Failed to copy');
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setTranscript('');
    setSummary('');
    setBlogPost('');
    setProgress('idle');
    setError(null);
    setStatusMessage('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const hasContent = transcript || summary || blogPost;
  const currentContent = activeTab === 'transcript' ? transcript : activeTab === 'summary' ? summary : blogPost;

  const progressSteps = [
    { key: 'uploading', label: 'Upload' },
    { key: 'transcribing', label: 'Transcribe' },
    { key: 'summarizing', label: 'Summarize' },
    { key: 'generating_blog', label: 'Blog Post' },
  ];

  const getStepStatus = (stepKey: string) => {
    const stepOrder = ['uploading', 'transcribing', 'summarizing', 'generating_blog', 'complete'];
    const currentIndex = stepOrder.indexOf(progress);
    const stepIndex = stepOrder.indexOf(stepKey);
    if (currentIndex > stepIndex) return 'complete';
    if (currentIndex === stepIndex) return 'active';
    return 'pending';
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Left Panel: File Upload */}
      <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-4 space-y-4">
        <h3 className="text-xl font-semibold text-white flex items-center gap-2">
          <Mic className="w-6 h-6 text-purple-500" />
          Transcribe Audio/Video
        </h3>

        <p className="text-gray-400 text-sm">
          Upload an audio or video file to generate a transcript, summary, and blog post.
        </p>

        {/* Drop Zone */}
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
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
              <FileAudio className="w-12 h-12 mx-auto text-green-400" />
              <p className="text-white font-medium">{selectedFile.name}</p>
              <p className="text-gray-400 text-sm">
                {(selectedFile.size / (1024 * 1024)).toFixed(1)} MB
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <Upload className="w-12 h-12 mx-auto text-gray-500" />
              <p className="text-gray-300">Drop file here or click to browse</p>
              <p className="text-gray-500 text-sm">MP3, WAV, MP4, WebM, etc. Max {MAX_SIZE_MB}MB</p>
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
                <Mic className="w-5 h-5" />
                Transcribe
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
                      <div className={`w-8 h-0.5 mx-1 ${status === 'complete' ? 'bg-green-500' : 'bg-gray-700'}`} />
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
      </div>

      {/* Right Panel: Output */}
      <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-4 space-y-4 h-[600px] flex flex-col">
        <h3 className="text-xl font-semibold text-white flex items-center gap-2">
          <FileAudio className="w-6 h-6 text-purple-500" />
          Results
        </h3>

        {!hasContent && !isProcessing && (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            <div className="text-center">
              <FileAudio className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p className="text-sm">Results will appear here after transcription.</p>
            </div>
          </div>
        )}

        {(hasContent || isProcessing) && (
          <>
            {/* Tab Buttons */}
            <div className="flex gap-2">
              {[
                { id: 'transcript', label: 'Transcript', content: transcript },
                { id: 'summary', label: 'Summary', content: summary },
                { id: 'blog', label: 'Blog Post', content: blogPost },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as OutputTab)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                    activeTab === tab.id
                      ? 'bg-purple-600 text-white'
                      : tab.content
                      ? 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                      : 'bg-gray-800 text-gray-500'
                  }`}
                >
                  {tab.label}
                  {tab.content && <Check className="w-3 h-3 text-green-400" />}
                </button>
              ))}
            </div>

            {/* Content Area */}
            <div className="flex-1 bg-gray-800/50 border border-gray-700 rounded-lg p-4 overflow-y-auto">
              {currentContent ? (
                <div className="prose prose-invert prose-sm max-w-none">
                  <pre className="whitespace-pre-wrap font-sans text-gray-200 text-sm leading-relaxed">
                    {currentContent}
                  </pre>
                </div>
              ) : isProcessing ? (
                <div className="flex items-center justify-center h-full text-gray-400">
                  <Loader2 className="w-6 h-6 animate-spin mr-2" />
                  <span>Generating...</span>
                </div>
              ) : (
                <div className="flex items-center justify-center h-full text-gray-500">
                  <span className="text-sm">Not yet generated</span>
                </div>
              )}
            </div>

            {/* Copy Button */}
            {currentContent && (
              <button
                onClick={() => handleCopy(currentContent, activeTab)}
                className="w-full py-2 rounded-lg text-sm font-medium bg-gray-700 hover:bg-gray-600 text-white flex items-center justify-center gap-2"
              >
                <Copy className="w-4 h-4" />
                Copy {activeTab === 'transcript' ? 'Transcript' : activeTab === 'summary' ? 'Summary' : 'Blog Post'}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
