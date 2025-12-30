'use client';

import { useState } from 'react';
import { Link, Loader2, Sparkles, Twitter, Linkedin, Check, AlertCircle } from 'lucide-react';

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
  source_url: string;
}

export default function URLPostBox({ token, connections, showNotification }: URLPostBoxProps) {
  const [url, setUrl] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [preview, setPreview] = useState<GeneratedContent | null>(null);
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
    setPreview(null);
    setPosted({ twitter: false, linkedin: false });

    try {
      const response = await fetch('/api/generate-from-url', {
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

      const data = await response.json();
      setPreview(data);
      showNotification('success', 'Posts generated! Review and click to post.');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate posts';
      setError(message);
      showNotification('error', message);
    } finally {
      setIsGenerating(false);
    }
  };

  const handlePost = async (platform: 'twitter' | 'linkedin') => {
    if (!preview || !token) return;

    setIsPosting(prev => ({ ...prev, [platform]: true }));

    try {
      const response = await fetch('/api/post-from-url', {
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
    setPreview(null);
    setPosted({ twitter: false, linkedin: false });
    setError(null);
  };

  return (
    <div className="space-y-6">
      {/* URL Input Card */}
      <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-6 hover:border-gray-700 transition-all">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-semibold text-white flex items-center gap-2">
            <Link className="w-6 h-6 text-purple-500" />
            Generate Post from URL
          </h3>
        </div>

        <p className="text-gray-400 text-sm mb-4">
          Paste a URL to an article, blog post, or webpage. The AI will read it and generate social media posts with an image.
        </p>

        <div className="mb-4">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/article"
            className="w-full bg-gray-800/50 border border-gray-700 rounded-lg p-4 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20"
            disabled={isGenerating}
          />
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-900/20 border border-red-700/30 rounded-lg flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-red-400" />
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
                Generating... (this may take a minute)
              </>
            ) : (
              <>
                <Sparkles className="w-5 h-5" />
                Generate Posts
              </>
            )}
          </button>

          {preview && (
            <button
              onClick={handleReset}
              className="py-3 px-4 rounded-lg font-medium transition-all bg-gray-700 hover:bg-gray-600 text-white"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Preview Card */}
      {preview && (
        <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-6">
          <h3 className="text-xl font-semibold text-white mb-4">Preview</h3>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Image Preview */}
            {preview.image_base64 && (
              <div className="lg:row-span-2">
                <p className="text-sm text-gray-400 mb-2">Generated Image</p>
                <img
                  src={`data:image/png;base64,${preview.image_base64}`}
                  alt="Generated post image"
                  className="w-full rounded-lg border border-gray-700"
                />
              </div>
            )}

            {/* X/Twitter Post */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-400 flex items-center gap-2">
                  <Twitter className="w-4 h-4" />
                  X/Twitter Post
                </p>
                <span className="text-xs text-gray-500">
                  {preview.x_post?.length || 0} chars
                </span>
              </div>
              <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
                <p className="text-white text-sm whitespace-pre-wrap">
                  {preview.x_post || 'No X post generated'}
                </p>
              </div>
              <button
                onClick={() => handlePost('twitter')}
                disabled={!preview.x_post || !connections.twitter || isPosting.twitter || posted.twitter}
                className={`w-full py-2 px-4 rounded-lg font-medium transition-all flex items-center justify-center gap-2 ${
                  posted.twitter
                    ? 'bg-green-600 text-white'
                    : 'bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50 disabled:cursor-not-allowed'
                }`}
              >
                {isPosting.twitter ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Posting...
                  </>
                ) : posted.twitter ? (
                  <>
                    <Check className="w-4 h-4" />
                    Posted!
                  </>
                ) : !connections.twitter ? (
                  'Connect X first'
                ) : (
                  <>
                    <Twitter className="w-4 h-4" />
                    Post to X
                  </>
                )}
              </button>
            </div>

            {/* LinkedIn Post */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-400 flex items-center gap-2">
                  <Linkedin className="w-4 h-4" />
                  LinkedIn Post
                </p>
                <span className="text-xs text-gray-500">
                  {preview.linkedin_post?.length || 0} chars
                </span>
              </div>
              <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 max-h-48 overflow-y-auto">
                <p className="text-white text-sm whitespace-pre-wrap">
                  {preview.linkedin_post || 'No LinkedIn post generated'}
                </p>
              </div>
              <button
                onClick={() => handlePost('linkedin')}
                disabled={!preview.linkedin_post || !connections.linkedin || isPosting.linkedin || posted.linkedin}
                className={`w-full py-2 px-4 rounded-lg font-medium transition-all flex items-center justify-center gap-2 ${
                  posted.linkedin
                    ? 'bg-green-600 text-white'
                    : 'bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-50 disabled:cursor-not-allowed'
                }`}
              >
                {isPosting.linkedin ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Posting...
                  </>
                ) : posted.linkedin ? (
                  <>
                    <Check className="w-4 h-4" />
                    Posted!
                  </>
                ) : !connections.linkedin ? (
                  'Connect LinkedIn first'
                ) : (
                  <>
                    <Linkedin className="w-4 h-4" />
                    Post to LinkedIn
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Source URL */}
          <div className="mt-4 pt-4 border-t border-gray-800">
            <p className="text-xs text-gray-500">
              Source: <a href={preview.source_url} target="_blank" rel="noopener noreferrer" className="text-purple-400 hover:underline">{preview.source_url}</a>
            </p>
          </div>
        </div>
      )}

      {/* Connection Warning */}
      {!connections.twitter && !connections.linkedin && (
        <div className="bg-yellow-900/20 border border-yellow-700/30 rounded-lg p-4">
          <p className="text-sm text-yellow-400">
            Connect at least one platform in the Campaign tab to post generated content.
          </p>
        </div>
      )}
    </div>
  );
}
