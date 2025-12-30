'use client';

import { useState, useRef, useEffect } from 'react';
import { MessageSquare, Send, Loader2, Twitter, Linkedin, Image, Trash2, Sparkles, Check, AlertCircle } from 'lucide-react';

interface PostBuilderProps {
  token: string | null;
  connections: {
    twitter: boolean;
    linkedin: boolean;
  };
  showNotification: (type: 'success' | 'error' | 'info', message: string) => void;
}

interface Message {
  role: 'user' | 'model';
  content: string;
}

interface ParsedPosts {
  x_post: string | null;
  linkedin_post: string | null;
  source_url?: string | null;
  visual_style?: string | null;
}

interface CampaignConfig {
  campaign_prompt: string;
  refined_persona: string;
  visual_style: string;
}

export default function PostBuilder({ token, connections, showNotification }: PostBuilderProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [parsedPosts, setParsedPosts] = useState<ParsedPosts>({ x_post: null, linkedin_post: null, source_url: null });
  const [campaignConfig, setCampaignConfig] = useState<CampaignConfig | null>(null);
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [isGeneratingImage, setIsGeneratingImage] = useState(false);
  const [isPosting, setIsPosting] = useState<{ twitter: boolean; linkedin: boolean }>({
    twitter: false,
    linkedin: false
  });
  const [posted, setPosted] = useState<{ twitter: boolean; linkedin: boolean }>({
    twitter: false,
    linkedin: false
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  // Parse posts and campaign config from message content
  const parseToolCallsFromContent = (content: string): { posts: ParsedPosts; campaign: CampaignConfig | null } => {
    const posts: ParsedPosts = { x_post: null, linkedin_post: null, source_url: null, visual_style: null };
    let campaign: CampaignConfig | null = null;

    // Check for base64 encoded tool call format
    const b64Match = content.match(/__TOOL_CALL_B64__([\w+/=]+)__END_TOOL_CALL__/);
    if (b64Match) {
      try {
        const decoded = atob(b64Match[1]);
        const toolData = JSON.parse(decoded);

        if (toolData.tool === 'generate_posts') {
          posts.x_post = toolData.x_post || null;
          posts.linkedin_post = toolData.linkedin_post || null;
          posts.source_url = toolData.source_url || null;
          posts.visual_style = toolData.visual_style || null;
        } else if (toolData.tool === 'create_campaign_prompt') {
          campaign = {
            campaign_prompt: toolData.campaign_prompt || '',
            refined_persona: toolData.refined_persona || '',
            visual_style: toolData.visual_style || ''
          };
        }
      } catch (e) {
        console.error('Failed to parse b64 tool call:', e);
      }
    }

    return { posts, campaign };
  };

  // Legacy parser for text markers
  const parsePostsFromContent = (content: string): ParsedPosts => {
    const { posts } = parseToolCallsFromContent(content);
    return posts;
  };

  // Update parsed posts and campaign config whenever messages change
  useEffect(() => {
    // Find the most recent AI message with tool calls
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'model') {
        const { posts, campaign } = parseToolCallsFromContent(messages[i].content);

        if (posts.x_post || posts.linkedin_post) {
          setParsedPosts(posts);
          // Auto-generate image if we don't have one yet
          // Pass visual_style so image matches the persona (e.g., "Mario and Luigi cartoon style")
          if (!imageBase64 && !isGeneratingImage && token) {
            generateImageAuto(posts.x_post || posts.linkedin_post || '', posts.visual_style);
          }
          return;
        }

        if (campaign) {
          setCampaignConfig(campaign);
          return;
        }
      }
    }
  }, [messages]);

  // Auto-generate image function
  const generateImageAuto = async (postText: string, visualStyle?: string | null) => {
    if (!postText || !token || isGeneratingImage) return;

    setIsGeneratingImage(true);
    try {
      const response = await fetch('/api/chat/generate-image', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          post_text: postText,
          visual_style: visualStyle || undefined
        })
      });

      if (response.ok) {
        const data = await response.json();
        setImageBase64(data.image_base64);
      }
    } catch (err) {
      console.error('Auto image generation failed:', err);
    } finally {
      setIsGeneratingImage(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || isStreaming || !token) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsStreaming(true);
    setStreamingContent('');

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          message: userMessage,
          history: messages.map(m => ({ role: m.role, content: m.content }))
        })
      });

      if (!response.ok) {
        throw new Error('Failed to send message');
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      const decoder = new TextDecoder();
      let fullContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') {
              continue;
            }
            fullContent += data;
            setStreamingContent(fullContent);

            // Parse posts as they stream in
            const parsed = parsePostsFromContent(fullContent);
            if (parsed.x_post || parsed.linkedin_post) {
              setParsedPosts(parsed);
            }
          }
        }
      }

      // Add the complete message to history
      setMessages(prev => [...prev, { role: 'model', content: fullContent }]);
      setStreamingContent('');

    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to send message';
      showNotification('error', message);
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleGenerateImage = async () => {
    const postText = parsedPosts.x_post || parsedPosts.linkedin_post;
    if (!postText || !token) return;

    setIsGeneratingImage(true);

    try {
      const response = await fetch('/api/chat/generate-image', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ post_text: postText })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to generate image');
      }

      const data = await response.json();
      setImageBase64(data.image_base64);
      showNotification('success', 'Image generated!');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate image';
      showNotification('error', message);
    } finally {
      setIsGeneratingImage(false);
    }
  };

  const handlePost = async (platform: 'twitter' | 'linkedin') => {
    if (!token) return;

    const postText = platform === 'twitter' ? parsedPosts.x_post : parsedPosts.linkedin_post;
    if (!postText) return;

    setIsPosting(prev => ({ ...prev, [platform]: true }));

    try {
      const response = await fetch('/api/post-from-url', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          x_post: parsedPosts.x_post,
          linkedin_post: parsedPosts.linkedin_post,
          image_base64: imageBase64,
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

  const handleClearChat = () => {
    setMessages([]);
    setStreamingContent('');
    setParsedPosts({ x_post: null, linkedin_post: null, source_url: null });
    setCampaignConfig(null);
    setImageBase64(null);
    setPosted({ twitter: false, linkedin: false });
  };

  // Format message content for display (hide the markers)
  const formatMessageContent = (content: string) => {
    return content
      .replace(/__TOOL_CALL_B64__[\w+/=]+__END_TOOL_CALL__/g, '')
      .replace(/__TOOL_CALL__[\s\S]*?__END_TOOL_CALL__/g, '')
      .replace(/---X_POST_START---[\s\S]*?---X_POST_END---/g, '[X Post generated - see preview]')
      .replace(/---LINKEDIN_POST_START---[\s\S]*?---LINKEDIN_POST_END---/g, '[LinkedIn Post generated - see preview]')
      .trim();
  };

  const hasPosts = parsedPosts.x_post || parsedPosts.linkedin_post;
  const hasContent = hasPosts || campaignConfig;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Chat Panel */}
      <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg flex flex-col h-[600px]">
        {/* Header */}
        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
          <h3 className="text-xl font-semibold text-white flex items-center gap-2">
            <MessageSquare className="w-6 h-6 text-purple-500" />
            Post Builder
          </h3>
          {messages.length > 0 && (
            <button
              onClick={handleClearChat}
              className="p-2 text-gray-400 hover:text-white transition-colors"
              title="Clear chat"
            >
              <Trash2 className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && !streamingContent && (
            <div className="text-center text-gray-500 py-8">
              <MessageSquare className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg mb-2">Start brainstorming your post</p>
              <p className="text-sm">Tell me what you want to post about. I&apos;ll help you craft engaging content for X and LinkedIn.</p>
            </div>
          )}

          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-lg p-3 ${
                  message.role === 'user'
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-800 text-gray-200'
                }`}
              >
                <p className="whitespace-pre-wrap text-sm">{formatMessageContent(message.content)}</p>
              </div>
            </div>
          ))}

          {/* Streaming message */}
          {streamingContent && (
            <div className="flex justify-start">
              <div className="max-w-[85%] rounded-lg p-3 bg-gray-800 text-gray-200">
                <p className="whitespace-pre-wrap text-sm">{formatMessageContent(streamingContent)}</p>
                <span className="inline-block w-2 h-4 bg-purple-500 animate-pulse ml-1" />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="p-4 border-t border-gray-800">
          <div className="flex gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe your post idea..."
              className="flex-1 bg-gray-800/50 border border-gray-700 rounded-lg p-3 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 resize-none"
              rows={2}
              disabled={isStreaming}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming || !token}
              className="px-4 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg transition-colors flex items-center justify-center"
            >
              {isStreaming ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>

      {/* Preview Panel */}
      <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-4 space-y-4 h-[600px] overflow-y-auto">
        <h3 className="text-xl font-semibold text-white flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-purple-500" />
          Preview
        </h3>

        {!hasContent && (
          <div className="text-center text-gray-500 py-8">
            <Sparkles className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p className="text-sm">Posts will appear here when generated.</p>
            <p className="text-xs mt-2">Describe your idea and I&apos;ll search for content and generate posts!</p>
          </div>
        )}

        {/* X Post Preview */}
        {parsedPosts.x_post && (
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Twitter className="w-5 h-5 text-blue-400" />
                <span className="text-white font-medium">X / Twitter</span>
              </div>
              <span className={`text-xs ${parsedPosts.x_post.length > 280 ? 'text-red-400' : 'text-gray-400'}`}>
                {parsedPosts.x_post.length}/280
              </span>
            </div>
            <p className="text-gray-200 text-sm whitespace-pre-wrap mb-3">{parsedPosts.x_post}</p>
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
                <>
                  <Check className="w-4 h-4" />
                  Posted
                </>
              ) : connections.twitter ? (
                <>
                  <Twitter className="w-4 h-4" />
                  Post to X
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4" />
                  Connect X first
                </>
              )}
            </button>
          </div>
        )}

        {/* LinkedIn Post Preview */}
        {parsedPosts.linkedin_post && (
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Linkedin className="w-5 h-5 text-blue-500" />
                <span className="text-white font-medium">LinkedIn</span>
              </div>
              <span className="text-xs text-gray-400">
                {parsedPosts.linkedin_post.length} chars
              </span>
            </div>
            <p className="text-gray-200 text-sm whitespace-pre-wrap mb-3">{parsedPosts.linkedin_post}</p>
            <button
              onClick={() => handlePost('linkedin')}
              disabled={!connections.linkedin || isPosting.linkedin || posted.linkedin}
              className={`w-full py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                posted.linkedin
                  ? 'bg-green-600 text-white cursor-default'
                  : connections.linkedin
                    ? 'bg-blue-600 hover:bg-blue-700 text-white'
                    : 'bg-gray-700 text-gray-400 cursor-not-allowed'
              }`}
            >
              {isPosting.linkedin ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : posted.linkedin ? (
                <>
                  <Check className="w-4 h-4" />
                  Posted
                </>
              ) : connections.linkedin ? (
                <>
                  <Linkedin className="w-4 h-4" />
                  Post to LinkedIn
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4" />
                  Connect LinkedIn first
                </>
              )}
            </button>
          </div>
        )}

        {/* Image Preview */}
        {hasPosts && (
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Image className="w-5 h-5 text-purple-400" />
                <span className="text-white font-medium">Image</span>
              </div>
            </div>

            {imageBase64 ? (
              <img
                src={`data:image/png;base64,${imageBase64}`}
                alt="Generated post image"
                className="w-full rounded-lg mb-3"
              />
            ) : (
              <button
                onClick={handleGenerateImage}
                disabled={isGeneratingImage}
                className="w-full py-8 border-2 border-dashed border-gray-600 rounded-lg hover:border-purple-500 transition-colors flex flex-col items-center justify-center gap-2 text-gray-400 hover:text-purple-400"
              >
                {isGeneratingImage ? (
                  <>
                    <Loader2 className="w-8 h-8 animate-spin" />
                    <span className="text-sm">Generating image...</span>
                  </>
                ) : (
                  <>
                    <Image className="w-8 h-8" />
                    <span className="text-sm">Click to generate image</span>
                  </>
                )}
              </button>
            )}
          </div>
        )}

        {/* Campaign Config Preview */}
        {campaignConfig && (
          <div className="bg-purple-900/30 border border-purple-700 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-5 h-5 text-purple-400" />
              <span className="text-white font-medium">Campaign Configuration</span>
            </div>

            <div className="space-y-3 text-sm">
              <div>
                <label className="text-purple-300 text-xs uppercase tracking-wide">Campaign Prompt</label>
                <p className="text-gray-200 mt-1 bg-gray-800/50 p-2 rounded">{campaignConfig.campaign_prompt}</p>
              </div>

              <div>
                <label className="text-purple-300 text-xs uppercase tracking-wide">Persona</label>
                <p className="text-gray-200 mt-1 bg-gray-800/50 p-2 rounded">{campaignConfig.refined_persona}</p>
              </div>

              <div>
                <label className="text-purple-300 text-xs uppercase tracking-wide">Visual Style</label>
                <p className="text-gray-200 mt-1 bg-gray-800/50 p-2 rounded">{campaignConfig.visual_style}</p>
              </div>
            </div>

            <button
              onClick={() => {
                navigator.clipboard.writeText(campaignConfig.campaign_prompt);
                showNotification('success', 'Campaign prompt copied to clipboard!');
              }}
              className="w-full mt-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Copy Campaign Prompt
            </button>
          </div>
        )}

        {/* Source URL */}
        {parsedPosts.source_url && (
          <div className="text-xs text-gray-400 flex items-center gap-1">
            <span>📎 Source:</span>
            <a href={parsedPosts.source_url} target="_blank" rel="noopener noreferrer" className="text-purple-400 hover:underline truncate">
              {parsedPosts.source_url}
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
