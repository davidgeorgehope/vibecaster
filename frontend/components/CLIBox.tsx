'use client';

import { useState, useEffect, useCallback } from 'react';
import { Terminal, Plus, Trash2, Copy, Check, Loader2, AlertCircle, Eye, EyeOff } from 'lucide-react';

interface CLIBoxProps {
  token: string | null;
  showNotification: (type: 'success' | 'error' | 'info', message: string) => void;
}

interface ApiKey {
  id: number;
  key_prefix: string;
  name: string;
  created_at: number;
  last_used_at: number | null;
  is_active: number;
}

export default function CLIBox({ token, showNotification }: CLIBoxProps) {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [revokeConfirm, setRevokeConfirm] = useState<number | null>(null);

  const loadKeys = useCallback(async () => {
    if (!token) return;

    try {
      const response = await fetch('/api/api-keys', {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setKeys(data);
      }
    } catch (error) {
      console.error('Failed to load API keys:', error);
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      loadKeys();
    }
  }, [token, loadKeys]);

  const handleCreate = async () => {
    if (!token || !newKeyName.trim()) return;

    setIsCreating(true);
    try {
      const response = await fetch('/api/api-keys', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: newKeyName.trim() })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create API key');
      }

      const data = await response.json();
      setNewlyCreatedKey(data.key);
      setNewKeyName('');
      setShowCreateForm(false);
      setShowKey(true);
      loadKeys();
      showNotification('success', 'API key created successfully');
    } catch (error) {
      showNotification('error', error instanceof Error ? error.message : 'Failed to create API key');
    } finally {
      setIsCreating(false);
    }
  };

  const handleRevoke = async (keyId: number) => {
    if (!token) return;

    try {
      const response = await fetch(`/api/api-keys/${keyId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        throw new Error('Failed to revoke API key');
      }

      setRevokeConfirm(null);
      loadKeys();
      showNotification('success', 'API key revoked');
    } catch (error) {
      showNotification('error', 'Failed to revoke API key');
    }
  };

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      showNotification('error', 'Failed to copy to clipboard');
    }
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  if (isLoading) {
    return (
      <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 text-purple-500 animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Terminal className="w-6 h-6 text-purple-500" />
          <h2 className="text-xl font-semibold text-white">CLI</h2>
        </div>
        {!showCreateForm && !newlyCreatedKey && (
          <button
            onClick={() => setShowCreateForm(true)}
            className="flex items-center gap-2 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            Create Key
          </button>
        )}
      </div>

      <p className="text-sm text-gray-400 mb-4">
        Use the CLI to manage campaigns, generate posts, and automate your social media from the terminal.
      </p>

      {/* Quick Start */}
      <div className="mb-6 p-4 bg-gray-800/50 border border-gray-700 rounded-lg">
        <h3 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-3">Quick Start</h3>
        <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-1">
          <p className="text-gray-500"># Run directly with npx (no install needed)</p>
          <p>npx vibecaster login</p>
          <p className="text-gray-500 mt-3"># Or install globally</p>
          <p>npm install -g vibecaster</p>
        </div>
      </div>

      {/* Newly created key warning */}
      {newlyCreatedKey && (
        <div className="mb-6 p-4 bg-yellow-900/20 border border-yellow-700/30 rounded-lg">
          <div className="flex items-start gap-2 mb-3">
            <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-yellow-400 font-medium">Save your API key now</p>
              <p className="text-yellow-400/70 text-sm mt-1">
                This key will only be shown once. Copy it and store it securely.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 bg-gray-950/50 rounded-lg p-3 font-mono text-sm">
            <code className="flex-1 text-green-400 break-all">
              {showKey ? newlyCreatedKey : '\u2022'.repeat(newlyCreatedKey.length)}
            </code>
            <button
              onClick={() => setShowKey(!showKey)}
              className="p-1.5 text-gray-400 hover:text-white transition-colors flex-shrink-0"
              title={showKey ? 'Hide key' : 'Show key'}
            >
              {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
            <button
              onClick={() => handleCopy(newlyCreatedKey)}
              className="p-1.5 text-gray-400 hover:text-white transition-colors flex-shrink-0"
              title="Copy key"
            >
              {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <button
            onClick={() => { setNewlyCreatedKey(null); setShowKey(false); }}
            className="mt-3 text-sm text-gray-400 hover:text-white transition-colors"
          >
            I&apos;ve saved my key
          </button>
        </div>
      )}

      {/* Create form */}
      {showCreateForm && (
        <div className="mb-6 p-4 bg-gray-800/50 border border-gray-700 rounded-lg">
          <label className="block text-sm text-gray-300 mb-2">Key Name</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="e.g., CLI Tool, CI/CD Pipeline"
              className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-purple-500"
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              autoFocus
            />
            <button
              onClick={handleCreate}
              disabled={isCreating || !newKeyName.trim()}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded-lg transition-colors"
            >
              {isCreating ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Create'}
            </button>
            <button
              onClick={() => { setShowCreateForm(false); setNewKeyName(''); }}
              className="px-3 py-2 text-gray-400 hover:text-white text-sm transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* API Keys Section */}
      <div className="mb-6">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">API Keys</h3>
        {keys.length === 0 ? (
          <div className="text-center py-6 text-gray-500">
            <Terminal className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>No API keys yet</p>
            <p className="text-sm mt-1">Create one to use the CLI</p>
          </div>
        ) : (
          <div className="space-y-2">
            {keys.map((key) => (
              <div
                key={key.id}
                className={`flex items-center justify-between p-3 rounded-lg border ${
                  key.is_active
                    ? 'bg-gray-800/30 border-gray-700/50'
                    : 'bg-gray-900/30 border-gray-800/30 opacity-60'
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-white font-medium text-sm">{key.name}</span>
                    {!key.is_active && (
                      <span className="text-xs px-1.5 py-0.5 bg-red-900/30 text-red-400 rounded">Revoked</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                    <code className="text-gray-400">{key.key_prefix}...</code>
                    <span>Created {formatDate(key.created_at)}</span>
                    {key.last_used_at && (
                      <span>Last used {formatDate(key.last_used_at)}</span>
                    )}
                  </div>
                </div>
                {key.is_active && (
                  <div>
                    {revokeConfirm === key.id ? (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-red-400">Revoke?</span>
                        <button
                          onClick={() => handleRevoke(key.id)}
                          className="px-2 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded transition-colors"
                        >
                          Yes
                        </button>
                        <button
                          onClick={() => setRevokeConfirm(null)}
                          className="px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
                        >
                          No
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setRevokeConfirm(key.id)}
                        className="p-1.5 text-gray-500 hover:text-red-400 transition-colors"
                        title="Revoke key"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* CLI Commands Guide */}
      <div className="border-t border-gray-700 pt-6">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <span className="text-2xl">⌨️</span> CLI Commands
        </h3>

        {/* Configure */}
        <div className="mb-6">
          <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-2">Configure</h4>
          <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-1">
            <p className="text-gray-500"># Login with your API key</p>
            <p>npx vibecaster login</p>
            <p className="text-gray-500 mt-1"># → API URL: https://vibecaster.ai/api</p>
            <p className="text-gray-500"># → API Key: vb_your_key_here</p>
          </div>
        </div>

        {/* Usage */}
        <div className="mb-6">
          <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-2">Commands</h4>
          <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-2">
            <div className="grid grid-cols-[180px_1fr] gap-x-4 gap-y-1">
              <span className="text-purple-400">npx vibecaster status</span>
              <span className="text-gray-400">Check connection & campaign status</span>
              <span className="text-purple-400">npx vibecaster campaign</span>
              <span className="text-gray-400">View your active campaign</span>
              <span className="text-purple-400">npx vibecaster create</span>
              <span className="text-gray-400">AI-generate a post from a prompt</span>
              <span className="text-purple-400">npx vibecaster generate</span>
              <span className="text-gray-400">Generate a post from URL (preview)</span>
              <span className="text-purple-400">npx vibecaster run</span>
              <span className="text-gray-400">Trigger immediate campaign run</span>
              <span className="text-purple-400">npx vibecaster post</span>
              <span className="text-gray-400">Post custom text/media directly</span>
              <span className="text-purple-400">npx vibecaster keys</span>
              <span className="text-gray-400">List your API keys</span>
            </div>
          </div>
        </div>

        {/* Direct Post */}
        <div className="mb-6">
          <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-2">Direct Posting</h4>
          <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-1">
            <p className="text-gray-500"># Post text to LinkedIn</p>
            <p>npx vibecaster post &quot;Your post text here&quot; --platform linkedin</p>
            <p className="text-gray-500 mt-3"># Post with an image</p>
            <p>npx vibecaster post &quot;Caption here&quot; --media image.png --platform linkedin</p>
            <p className="text-gray-500 mt-3"># Post video to X</p>
            <p>npx vibecaster post &quot;Check this out&quot; --media video.mp4 --platform twitter</p>
          </div>
        </div>

        {/* API Usage */}
        <div className="mb-6">
          <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-2">API Authentication</h4>
          <p className="text-sm text-gray-400 mb-2">
            Include your API key in the <code className="text-purple-300 bg-gray-800 px-1 rounded">X-API-Key</code> header:
          </p>
          <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-1">
            <p>curl -H &quot;X-API-Key: vb_your_key&quot; \</p>
            <p>  https://vibecaster.ai/api/campaign</p>
          </div>
        </div>

        {/* OpenClaw Skill */}
        <div>
          <h4 className="text-sm font-semibold text-purple-400 uppercase tracking-wide mb-2">OpenClaw Integration</h4>
          <p className="text-sm text-gray-400 mb-2">
            If you use <a href="https://openclaw.ai" className="text-purple-400 hover:text-purple-300 underline" target="_blank" rel="noopener noreferrer">OpenClaw</a>, Vibecaster has a built-in skill. Your AI assistant can post directly:
          </p>
          <div className="bg-gray-950/70 rounded-lg p-4 font-mono text-sm text-gray-300 space-y-1">
            <p className="text-gray-500"># Tell your assistant:</p>
            <p className="text-green-400">&quot;Post to LinkedIn: Just shipped a new feature...&quot;</p>
            <p className="text-gray-500 mt-2"># It will generate an image, write the copy,</p>
            <p className="text-gray-500"># and use `vibecaster post` to publish it.</p>
          </div>
        </div>
      </div>

    </div>
  );
}
