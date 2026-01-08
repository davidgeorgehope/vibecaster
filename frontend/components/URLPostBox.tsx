'use client';

import { useState, useRef } from 'react';
import { Link, Loader2, Sparkles, Twitter, Linkedin, Check, AlertCircle, Image, ExternalLink } from 'lucide-react';
import { fetchWithRetry } from '@/utils/fetchWithRetry';

interface URLPostBoxProps {
  token: string | null;
  connections: {
    twitter: boolean;
    linkedin: boolean;
  };
  showNotification: (type: 'success' | 'error' | 'info', message: string) => void;
}

interface GeneratedContent {
  x_post: string | null;
  linkedin_post: string | null;
  image_base64: string | null;
  source_url: string | null;
  title: string | null;
}

export default function URLPostBox({ token, connections, showNotification }: URLPostBoxProps) {
  const [url, setUrl] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [streamingStatus, setStreamingStatus] = useState<string>('');
  const [completedSteps, setCompletedSteps] = useState<string[]>([]);
  const [preview, setPreview] = useState<GeneratedContent>({
    x_post: null,
    linkedin_post: null,
    image_base64: null,
    source_url: null,
    title: null
  });
  const [isPosting, setIsPosting] = useState<{ twitter: boolean; linkedin: boolean }>({
    twitter: false,
    linkedin: false
  });
  const [posted, setPosted] = useState<{ twitter: boolean; linkedin: boolean }>({
    twitter: false,
    linkedin: false
  });
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    if (!url.trim()) return;
    if (!token) return;

    setIsGenerating(true);
    setError(null);
    setCompletedSteps([]);
    setPreview({
      x_post: null,
      linkedin_post: null,
      image_base64: null,
      source_url: null,
      title: null
    });
    setPosted({ twitter: false, linkedin: false });
    setStreamingStatus('Connecting...');

    try {
      const response = await fetchWithRetry('/api/generate-from-url-stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ url: url.trim() })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to generate posts');
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

        // SSE events are separated by double newlines
        const events = buffer.split('\n\n');
        // Keep the last incomplete chunk in the buffer
        buffer = events.pop() || '';

        for (const event of events) {
          const lines = event.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6);
              if (dataStr === '[DONE]') continue;

              try {
                const data = JSON.parse(dataStr);

              // Update status message
              if (data.message) {
                setStreamingStatus(data.message);
              }

              // Handle different status updates
              switch (data.status) {
                case 'fetching':
                  // Starting to fetch - no completed step yet
                  break;
                case 'content':
                  setCompletedSteps(prev => [...prev, 'Fetched URL content']);
                  setPreview(prev => ({
                    ...prev,
                    title: data.title,
                    source_url: data.source_url
                  }));
                  break;
                case 'generating_x':
                  // About to generate X post
                  break;
                case 'x_post':
                  setCompletedSteps(prev => [...prev, 'Generated X post']);
                  setPreview(prev => ({ ...prev, x_post: data.x_post }));
                  break;
                case 'x_post_error':
                  setCompletedSteps(prev => [...prev, 'X post failed']);
                  console.error('X post generation failed:', data.error);
                  break;
                case 'generating_linkedin':
                  // About to generate LinkedIn post
                  break;
                case 'linkedin_post':
                  setCompletedSteps(prev => [...prev, 'Generated LinkedIn post']);
                  setPreview(prev => ({ ...prev, linkedin_post: data.linkedin_post }));
                  break;
                case 'linkedin_post_error':
                  setCompletedSteps(prev => [...prev, 'LinkedIn post failed']);
                  console.error('LinkedIn post generation failed:', data.error);
                  break;
                case 'generating_image':
                  // About to generate image
                  break;
                case 'image':
                  setCompletedSteps(prev => [...prev, 'Generated image']);
                  setPreview(prev => ({ ...prev, image_base64: data.image_base64 }));
                  break;
                case 'image_error':
                  setCompletedSteps(prev => [...prev, 'Image generation failed']);
                  console.error('Image generation failed:', data.error);
                  break;
                case 'complete':
                  setStreamingStatus('');
                  showNotification('success', 'Posts generated! Review and click to post.');
                  break;
                case 'error':
                  throw new Error(data.error);
              }
            } catch (parseErr) {
              // Ignore JSON parse errors for partial chunks
            }
            }
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate posts';
      setError(message);
      showNotification('error', message);
    } finally {
      setIsGenerating(false);
      setStreamingStatus('');
    }
  };

  const handlePost = async (platform: 'twitter' | 'linkedin') => {
    if (!token) return;

    setIsPosting(prev => ({ ...prev, [platform]: true }));

    try {
      const response = await fetchWithRetry('/api/post-from-url', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          x_post: preview.x_post,
          linkedin_post: preview.linkedin_post,
          image_base64: preview.image_base64,
          platforms: [platform]
        })
      });

      const data = await response.json();

      if (data.posted?.includes(platform)) {
        setPosted(prev => ({ ...prev, [platform]: true }));
        showNotification('success', `Posted to ${platform === 'twitter' ? 'X/Twitter' : 'LinkedIn'}!`);
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

  const handleReset = () => {
    setUrl('');
    setPreview({
      x_post: null,
      linkedin_post: null,
      image_base64: null,
      source_url: null,
      title: null
    });
    setPosted({ twitter: false, linkedin: false });
    setError(null);
    setStreamingStatus('');
    setCompletedSteps([]);
  };

  const hasContent = preview.x_post || preview.linkedin_post || preview.image_base64;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Left Panel: URL Input */}
      <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-4 space-y-4">
        <h3 className="text-xl font-semibold text-white flex items-center gap-2">
          <Link className="w-6 h-6 text-purple-500" />
          Generate from URL
        </h3>

        <p className="text-gray-400 text-sm">
          Paste a URL to an article or blog post. Posts will appear as they are generated.
        </p>

        <div>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/article"
            className="w-full bg-gray-800/50 border border-gray-700 rounded-lg p-4 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20"
            disabled={isGenerating}
            onKeyDown={(e) => e.key === 'Enter' && handleGenerate()}
          />
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
            disabled={isGenerating || !url.trim()}
            className="flex-1 py-3 px-4 rounded-lg font-medium transition-all bg-gradient-to-r from-purple-600 to-pink-600 hover:opacity-90 text-white neon-glow disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isGenerating ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                {streamingStatus || 'Generating...'}
              </>
            ) : (
              <>
                <Sparkles className="w-5 h-5" />
                Generate Posts
              </>
            )}
          </button>

          {hasContent && (
            <button
              onClick={handleReset}
              className="py-3 px-4 rounded-lg font-medium transition-all bg-gray-700 hover:bg-gray-600 text-white"
            >
              Clear
            </button>
          )}
        </div>

        {/* Status/Progress */}
        {isGenerating && (completedSteps.length > 0 || streamingStatus) && (
          <div className="p-3 bg-purple-900/20 border border-purple-700/30 rounded-lg space-y-2">
            {/* Completed steps */}
            {completedSteps.map((step, index) => (
              <div key={index} className="flex items-center gap-2 text-xs text-green-400">
                <Check className="w-3 h-3" />
                <span>{step}</span>
              </div>
            ))}
            {/* Current status */}
            {streamingStatus && (
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                <p className="text-sm text-purple-300">{streamingStatus}</p>
              </div>
            )}
          </div>
        )}

        {/* Content Title */}
        {preview.title && (
          <div className="p-3 bg-gray-800/50 border border-gray-700 rounded-lg">
            <p className="text-xs text-gray-500 mb-1">Source Content</p>
            <p className="text-sm text-white font-medium">{preview.title}</p>
            {preview.source_url && (
              <a
                href={preview.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-purple-400 hover:underline flex items-center gap-1 mt-1"
              >
                <ExternalLink className="w-3 h-3" />
                {preview.source_url.slice(0, 50)}...
              </a>
            )}
          </div>
        )}

        {/* Connection Warning */}
        {!connections.twitter && !connections.linkedin && (
          <div className="p-3 bg-yellow-900/20 border border-yellow-700/30 rounded-lg">
            <p className="text-sm text-yellow-400">
              Connect at least one platform in the Campaign tab to post.
            </p>
          </div>
        )}
      </div>

      {/* Right Panel: Preview (PostBuilder style) */}
      <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-4 space-y-4 h-[600px] overflow-y-auto">
        <h3 className="text-xl font-semibold text-white flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-purple-500" />
          Preview
        </h3>

        {!hasContent && !isGenerating && (
          <div className="text-center text-gray-500 py-8">
            <Sparkles className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p className="text-sm">Posts will appear here as they are generated.</p>
          </div>
        )}

        {/* X/Twitter Post Card */}
        {(preview.x_post || (isGenerating && streamingStatus?.includes('X'))) && (
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Twitter className="w-5 h-5 text-blue-400" />
                <span className="text-white font-medium">X / Twitter</span>
              </div>
              {preview.x_post && (
                <span className={`text-xs ${preview.x_post.length > 280 ? 'text-red-400' : 'text-gray-400'}`}>
                  {preview.x_post.length}/280
                </span>
              )}
            </div>

            {preview.x_post ? (
              <>
                <p className="text-gray-200 text-sm whitespace-pre-wrap mb-3">{preview.x_post}</p>
                <button
                  onClick={() => handlePost('twitter')}
                  disabled={!connections.twitter || isPosting.twitter || posted.twitter}
                  className={`w-full py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    posted.twitter
                      ? 'bg-green-600 text-white cursor-default'
                      : connections.twitter
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
        {(preview.linkedin_post || (isGenerating && streamingStatus?.includes('LinkedIn'))) && (
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Linkedin className="w-5 h-5 text-blue-500" />
                <span className="text-white font-medium">LinkedIn</span>
              </div>
              {preview.linkedin_post && (
                <span className="text-xs text-gray-400">
                  {preview.linkedin_post.length} chars
                </span>
              )}
            </div>

            {preview.linkedin_post ? (
              <>
                <p className="text-gray-200 text-sm whitespace-pre-wrap mb-3 max-h-48 overflow-y-auto">
                  {preview.linkedin_post}
                </p>
                <button
                  onClick={() => handlePost('linkedin')}
                  disabled={!connections.linkedin || isPosting.linkedin || posted.linkedin}
                  className={`w-full py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    posted.linkedin
                      ? 'bg-green-600 text-white cursor-default'
                      : connections.linkedin
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

        {/* Image Card */}
        {(preview.image_base64 || (isGenerating && streamingStatus?.includes('image'))) && (
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <Image className="w-5 h-5 text-purple-400" />
              <span className="text-white font-medium">Image</span>
            </div>

            {preview.image_base64 ? (
              <img
                src={`data:image/png;base64,${preview.image_base64}`}
                alt="Generated post image"
                className="w-full rounded-lg"
              />
            ) : (
              <div className="flex items-center justify-center py-8 text-gray-400">
                <Loader2 className="w-6 h-6 animate-spin mr-2" />
                <span className="text-sm">Generating image...</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
