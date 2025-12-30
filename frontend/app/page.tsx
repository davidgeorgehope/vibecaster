'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import ConnectionBox from '@/components/ConnectionBox';
import PromptBox from '@/components/PromptBox';
import { Zap, AlertCircle, LogOut, Megaphone, Link } from 'lucide-react';
import URLPostBox from '@/components/URLPostBox';

type Tab = 'campaign' | 'url';

interface ConnectionStatus {
  twitter: boolean;
  linkedin: boolean;
}

export default function Home() {
  const { user, token, logout, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const [connections, setConnections] = useState<ConnectionStatus>({
    twitter: false,
    linkedin: false
  });
  const [notification, setNotification] = useState<{
    type: 'success' | 'error' | 'info';
    message: string;
  } | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('campaign');

  // Define helper functions with useCallback before useEffect hooks
  const showNotification = useCallback((type: 'success' | 'error' | 'info', message: string) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 5000);
  }, []);

  const loadConnectionStatus = useCallback(async () => {
    if (!token) return;
    try {
      const response = await fetch('/api/auth/status', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await response.json();
      setConnections(data);
    } catch (error) {
      console.error('Failed to load connection status:', error);
    }
  }, [token]);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !token) {
      router.push('/login');
    }
  }, [authLoading, token, router]);

  // Load connection status when token becomes available
  useEffect(() => {
    if (token) {
      loadConnectionStatus();
    }
  }, [token, loadConnectionStatus]);

  // Check for OAuth callback status in URL (separate useEffect)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get('status');
    const error = params.get('error');

    if (status === 'twitter_connected') {
      showNotification('success', 'Successfully connected to X (Twitter)!');
      if (token) {
        loadConnectionStatus();
      }
      // Clean up URL
      window.history.replaceState({}, '', '/');
    } else if (status === 'linkedin_connected') {
      showNotification('success', 'Successfully connected to LinkedIn!');
      if (token) {
        loadConnectionStatus();
      }
      // Clean up URL
      window.history.replaceState({}, '', '/');
    } else if (status === 'twitter_error' || status === 'linkedin_error') {
      showNotification('error', `Failed to connect: ${error || 'Unknown error'}`);
      window.history.replaceState({}, '', '/');
    }
  }, [token, loadConnectionStatus, showNotification]);

  const handleTwitterConnect = async () => {
    if (!token) return;
    try {
      const response = await fetch('/api/auth/twitter/login', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await response.json();
      if (data.auth_url) {
        window.location.href = data.auth_url;
      }
    } catch (error) {
      showNotification('error', 'Failed to initiate Twitter connection');
    }
  };

  const handleTwitterDisconnect = async () => {
    if (!token) return;
    try {
      const response = await fetch('/api/auth/twitter/disconnect', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        showNotification('success', 'Disconnected from X (Twitter)');
        loadConnectionStatus();
      }
    } catch (error) {
      showNotification('error', 'Failed to disconnect from Twitter');
    }
  };

  const handleLinkedInConnect = async () => {
    if (!token) return;
    try {
      const response = await fetch('/api/auth/linkedin/login', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await response.json();
      if (data.auth_url) {
        window.location.href = data.auth_url;
      }
    } catch (error) {
      showNotification('error', 'Failed to initiate LinkedIn connection');
    }
  };

  const handleLinkedInDisconnect = async () => {
    if (!token) return;
    try {
      const response = await fetch('/api/auth/linkedin/disconnect', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        showNotification('success', 'Disconnected from LinkedIn');
        loadConnectionStatus();
      }
    } catch (error) {
      showNotification('error', 'Failed to disconnect from LinkedIn');
    }
  };

  const handleActivateCampaign = async (prompt: string) => {
    if (!token) return;
    try {
      const response = await fetch('/api/setup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          user_prompt: prompt,
          schedule_cron: '0 9 * * *' // Daily at 9 AM
        })
      });

      if (!response.ok) {
        throw new Error('Failed to setup campaign');
      }

      const data = await response.json();
      showNotification('success', 'Campaign activated successfully! AI is analyzing your prompt...');
    } catch (error) {
      showNotification('error', 'Failed to activate campaign');
      throw error;
    }
  };

  const handleRunNow = async () => {
    if (!token) return;
    try {
      const response = await fetch('/api/run-now', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to run campaign');
      }

      showNotification('info', 'Campaign started! Check connected platforms for new posts.');
    } catch (error) {
      showNotification('error', 'Failed to run campaign');
      throw error;
    }
  };

  // Show loading state while checking authentication
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-950 via-purple-950/20 to-gray-950 flex items-center justify-center">
        <div className="text-center">
          <Zap className="w-12 h-12 text-purple-500 animate-pulse mx-auto mb-4" />
          <p className="text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  // Don't render if not authenticated (will redirect)
  if (!token) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-purple-950/20 to-gray-950">
      {/* Notification */}
      {notification && (
        <div className={`fixed top-4 right-4 z-50 p-4 rounded-lg shadow-lg border backdrop-blur-sm animate-in slide-in-from-top ${
          notification.type === 'success'
            ? 'bg-green-900/90 border-green-700 text-green-100'
            : notification.type === 'error'
            ? 'bg-red-900/90 border-red-700 text-red-100'
            : 'bg-blue-900/90 border-blue-700 text-blue-100'
        }`}>
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            <p>{notification.message}</p>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="border-b border-gray-800 backdrop-blur-sm bg-gray-900/50">
        <div className="container mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-3">
                <Zap className="w-8 h-8 text-purple-500" />
                <h1 className="text-4xl font-bold gradient-text">
                  VIBECASTER
                </h1>
              </div>
              <p className="text-gray-400 mt-2">
                AI-powered social media automation platform
              </p>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className="text-sm text-gray-400">Signed in as</p>
                <p className="text-white font-medium">{user?.email}</p>
              </div>
              <button
                onClick={logout}
                className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
                title="Logout"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b border-gray-800">
        <div className="container mx-auto px-6">
          <div className="flex gap-1">
            {[
              { id: 'campaign', label: 'Campaign', icon: Megaphone },
              { id: 'url', label: 'URL Post', icon: Link }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as Tab)}
                className={`flex items-center gap-2 px-4 py-3 font-medium transition-colors border-b-2 ${
                  activeTab === tab.id
                    ? 'text-purple-400 border-purple-500'
                    : 'text-gray-400 border-transparent hover:text-white'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-12">
        {activeTab === 'campaign' && (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 max-w-7xl mx-auto">
              {/* Box 1: Twitter Connection */}
              <ConnectionBox
                service="twitter"
                connected={connections.twitter}
                onConnect={handleTwitterConnect}
                onDisconnect={handleTwitterDisconnect}
              />

              {/* Box 2: LinkedIn Connection */}
              <ConnectionBox
                service="linkedin"
                connected={connections.linkedin}
                onConnect={handleLinkedInConnect}
                onDisconnect={handleLinkedInDisconnect}
              />

              {/* Box 3: Campaign Prompt */}
              <div className="lg:col-span-3">
                <PromptBox
                  onActivate={handleActivateCampaign}
                  onRunNow={handleRunNow}
                  token={token}
                />
              </div>
            </div>

            {/* Info Section */}
            <div className="max-w-7xl mx-auto mt-12">
              <div className="bg-gray-900/30 backdrop-blur-sm border border-gray-800 rounded-lg p-6">
                <h2 className="text-xl font-semibold text-white mb-4">How it works</h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-gray-300">
                  <div>
                    <div className="text-purple-400 font-semibold mb-2">1. Connect</div>
                    <p className="text-sm">Link your X (Twitter) and LinkedIn accounts securely via OAuth</p>
                  </div>
                  <div>
                    <div className="text-purple-400 font-semibold mb-2">2. Configure</div>
                    <p className="text-sm">Set your content prompt - AI will analyze and create a persona</p>
                  </div>
                  <div>
                    <div className="text-purple-400 font-semibold mb-2">3. Automate</div>
                    <p className="text-sm">AI generates and posts content daily using Google Gemini & Imagen</p>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}

        {activeTab === 'url' && (
          <div className="max-w-4xl mx-auto">
            <URLPostBox
              token={token}
              connections={connections}
              showNotification={showNotification}
            />
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 mt-12">
        <div className="container mx-auto px-6 py-6 text-center text-gray-500 text-sm">
          <p>Vibecaster - Local-first social media automation</p>
          <p className="mt-1">Powered by Google Gemini AI & Imagen</p>
        </div>
      </footer>
    </div>
  );
}
