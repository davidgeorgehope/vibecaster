'use client';

import { useState, useEffect, useCallback } from 'react';
import { Key, Plus, Trash2, Copy, Check, Loader2, AlertCircle, Eye, EyeOff } from 'lucide-react';

interface ApiKeysBoxProps {
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

export default function ApiKeysBox({ token, showNotification }: ApiKeysBoxProps) {
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
          <Key className="w-6 h-6 text-purple-500" />
          <h2 className="text-xl font-semibold text-white">API Keys</h2>
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
        Use API keys to authenticate with the Vibecaster CLI or API.
      </p>

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
              {showKey ? newlyCreatedKey : '•'.repeat(newlyCreatedKey.length)}
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

      {/* Keys list */}
      {keys.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <Key className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No API keys yet</p>
          <p className="text-sm mt-1">Create one to use the CLI or API</p>
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
  );
}
