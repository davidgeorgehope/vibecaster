'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { Zap, Users, FileText, BarChart3, ArrowLeft, RefreshCw, Twitter, Linkedin, Check, X, ChevronLeft, ChevronRight, AtSign, Plus, Pencil, Trash2 } from 'lucide-react';

interface Stats {
  total_users: number;
  active_campaigns: number;
  posts_today: number;
  total_posts: number;
  twitter_connections: number;
  linkedin_connections: number;
}

interface User {
  id: number;
  email: string;
  created_at: number;
  is_active: number;
  is_admin: number;
  connections: {
    twitter: boolean;
    linkedin: boolean;
  };
}

interface Campaign {
  id: number;
  user_id: number;
  email: string;
  user_prompt: string;
  refined_persona: string;
  visual_style: string;
  schedule_cron: string;
  last_run: number;
  include_links: number;
}

interface Post {
  id: number;
  user_id: number;
  email: string;
  post_text: string;
  topics: string[];
  platforms: string[];
  created_at: number;
}

interface LinkedInMention {
  id: number;
  company_name: string;
  organization_urn: string;
  aliases: string[];
  is_active: number;
  created_at: number;
  updated_at: number;
}

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

interface PaginationState {
  page: number;
  pages: number;
  total: number;
}

type Tab = 'stats' | 'users' | 'campaigns' | 'posts' | 'mentions';

export default function AdminPage() {
  const { token, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>('stats');
  const [stats, setStats] = useState<Stats | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [usersPagination, setUsersPagination] = useState<PaginationState>({ page: 1, pages: 1, total: 0 });
  const [campaignsPagination, setCampaignsPagination] = useState<PaginationState>({ page: 1, pages: 1, total: 0 });
  const [postsPagination, setPostsPagination] = useState<PaginationState>({ page: 1, pages: 1, total: 0 });
  const [mentions, setMentions] = useState<LinkedInMention[]>([]);
  const [editingMention, setEditingMention] = useState<number | null>(null);
  const [newMention, setNewMention] = useState({ company_name: '', organization_urn: '', aliases: '' });
  const [mentionError, setMentionError] = useState<string | null>(null);

  const fetchUsers = useCallback(async (page: number = 1) => {
    if (!token) return;
    const headers = { 'Authorization': `Bearer ${token}` };
    const res = await fetch(`/api/admin/users?page=${page}`, { headers });
    if (res.ok) {
      const data: PaginatedResponse<User> = await res.json();
      setUsers(data.items);
      setUsersPagination({ page: data.page, pages: data.pages, total: data.total });
    }
  }, [token]);

  const fetchCampaigns = useCallback(async (page: number = 1) => {
    if (!token) return;
    const headers = { 'Authorization': `Bearer ${token}` };
    const res = await fetch(`/api/admin/campaigns?page=${page}`, { headers });
    if (res.ok) {
      const data: PaginatedResponse<Campaign> = await res.json();
      setCampaigns(data.items);
      setCampaignsPagination({ page: data.page, pages: data.pages, total: data.total });
    }
  }, [token]);

  const fetchPosts = useCallback(async (page: number = 1) => {
    if (!token) return;
    const headers = { 'Authorization': `Bearer ${token}` };
    const res = await fetch(`/api/admin/posts?page=${page}`, { headers });
    if (res.ok) {
      const data: PaginatedResponse<Post> = await res.json();
      setPosts(data.items);
      setPostsPagination({ page: data.page, pages: data.pages, total: data.total });
    }
  }, [token]);

  const fetchMentions = useCallback(async () => {
    if (!token) return;
    const headers = { 'Authorization': `Bearer ${token}` };
    const res = await fetch('/api/admin/mentions?include_inactive=true', { headers });
    if (res.ok) {
      const data = await res.json();
      setMentions(data);
    }
  }, [token]);

  const createMention = async () => {
    if (!token) return;
    setMentionError(null);
    try {
      const res = await fetch('/api/admin/mentions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          company_name: newMention.company_name,
          organization_urn: newMention.organization_urn,
          aliases: newMention.aliases ? newMention.aliases.split(',').map(a => a.trim()).filter(Boolean) : []
        })
      });
      if (res.ok) {
        setNewMention({ company_name: '', organization_urn: '', aliases: '' });
        fetchMentions();
      } else {
        const data = await res.json();
        setMentionError(data.detail || 'Failed to create mention');
      }
    } catch {
      setMentionError('Failed to create mention');
    }
  };

  const updateMention = async (id: number, updates: { company_name?: string; organization_urn?: string; aliases?: string[]; is_active?: boolean }) => {
    if (!token) return;
    setMentionError(null);
    try {
      const res = await fetch(`/api/admin/mentions/${id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updates)
      });
      if (res.ok) {
        setEditingMention(null);
        fetchMentions();
      } else {
        const data = await res.json();
        setMentionError(data.detail || 'Failed to update mention');
      }
    } catch {
      setMentionError('Failed to update mention');
    }
  };

  const deleteMention = async (id: number) => {
    if (!token) return;
    if (!confirm('Are you sure you want to delete this mention?')) return;
    try {
      const res = await fetch(`/api/admin/mentions/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        fetchMentions();
      }
    } catch {
      setMentionError('Failed to delete mention');
    }
  };

  const toggleMentionActive = async (mention: LinkedInMention) => {
    await updateMention(mention.id, { is_active: !mention.is_active });
  };

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);

    try {
      const headers = { 'Authorization': `Bearer ${token}` };

      // Fetch stats first to check admin access
      const statsRes = await fetch('/api/admin/stats', { headers });
      if (statsRes.status === 403) {
        setError('You do not have admin access');
        setLoading(false);
        return;
      }
      if (!statsRes.ok) {
        throw new Error('Failed to fetch admin data');
      }
      const statsData = await statsRes.json();
      setStats(statsData);

      // Fetch paginated data in parallel
      await Promise.all([
        fetchUsers(1),
        fetchCampaigns(1),
        fetchPosts(1),
        fetchMentions()
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [token, fetchUsers, fetchCampaigns, fetchPosts, fetchMentions]);

  useEffect(() => {
    if (!authLoading && !token) {
      router.push('/login');
    }
  }, [authLoading, token, router]);

  useEffect(() => {
    if (token) {
      fetchData();
    }
  }, [token, fetchData]);

  const formatDate = (timestamp: number) => {
    if (!timestamp) return 'Never';
    return new Date(timestamp * 1000).toLocaleString();
  };

  const formatRelativeDate = (timestamp: number) => {
    if (!timestamp) return 'Never';
    const now = Date.now();
    const diff = now - timestamp * 1000;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
  };

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

  if (!token) return null;

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-950 via-purple-950/20 to-gray-950 flex items-center justify-center">
        <div className="text-center">
          <div className="bg-red-900/50 border border-red-700 rounded-lg p-6 max-w-md">
            <h2 className="text-xl font-semibold text-red-400 mb-2">Access Denied</h2>
            <p className="text-gray-400 mb-4">{error}</p>
            <button
              onClick={() => router.push('/')}
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors"
            >
              Go Back Home
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-purple-950/20 to-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 backdrop-blur-sm bg-gray-900/50">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push('/')}
                className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div className="flex items-center gap-3">
                <Zap className="w-6 h-6 text-purple-500" />
                <h1 className="text-2xl font-bold text-white">Admin Dashboard</h1>
              </div>
            </div>
            <button
              onClick={fetchData}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b border-gray-800">
        <div className="container mx-auto px-6">
          <div className="flex gap-1">
            {[
              { id: 'stats', label: 'Overview', icon: BarChart3 },
              { id: 'users', label: 'Users', icon: Users },
              { id: 'campaigns', label: 'Campaigns', icon: FileText },
              { id: 'posts', label: 'Posts', icon: FileText },
              { id: 'mentions', label: 'Mentions', icon: AtSign }
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

      {/* Content */}
      <main className="container mx-auto px-6 py-8">
        {loading && !stats ? (
          <div className="text-center py-12">
            <Zap className="w-8 h-8 text-purple-500 animate-pulse mx-auto mb-4" />
            <p className="text-gray-400">Loading data...</p>
          </div>
        ) : (
          <>
            {/* Stats Tab */}
            {activeTab === 'stats' && stats && (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                <StatCard label="Total Users" value={stats.total_users} />
                <StatCard label="Active Campaigns" value={stats.active_campaigns} />
                <StatCard label="Posts Today" value={stats.posts_today} />
                <StatCard label="Total Posts" value={stats.total_posts} />
                <StatCard label="Twitter Connected" value={stats.twitter_connections} icon={<Twitter className="w-4 h-4" />} />
                <StatCard label="LinkedIn Connected" value={stats.linkedin_connections} icon={<Linkedin className="w-4 h-4" />} />
              </div>
            )}

            {/* Users Tab */}
            {activeTab === 'users' && (
              <div className="space-y-4">
                <div className="bg-gray-900/50 border border-gray-800 rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-gray-800">
                        <th className="text-left px-4 py-3 text-gray-400 font-medium">ID</th>
                        <th className="text-left px-4 py-3 text-gray-400 font-medium">Email</th>
                        <th className="text-left px-4 py-3 text-gray-400 font-medium">Signed Up</th>
                        <th className="text-left px-4 py-3 text-gray-400 font-medium">Connections</th>
                        <th className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map(user => (
                        <tr key={user.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                          <td className="px-4 py-3 text-gray-300">{user.id}</td>
                          <td className="px-4 py-3">
                            <span className="text-white">{user.email}</span>
                            {user.is_admin ? (
                              <span className="ml-2 px-2 py-0.5 text-xs bg-purple-900/50 text-purple-300 rounded">Admin</span>
                            ) : null}
                          </td>
                          <td className="px-4 py-3 text-gray-400">{formatDate(user.created_at)}</td>
                          <td className="px-4 py-3">
                            <div className="flex gap-2">
                              <span className={`flex items-center gap-1 ${user.connections.twitter ? 'text-blue-400' : 'text-gray-600'}`}>
                                <Twitter className="w-4 h-4" />
                                {user.connections.twitter ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
                              </span>
                              <span className={`flex items-center gap-1 ${user.connections.linkedin ? 'text-blue-400' : 'text-gray-600'}`}>
                                <Linkedin className="w-4 h-4" />
                                {user.connections.linkedin ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-1 text-xs rounded ${
                              user.is_active ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                            }`}>
                              {user.is_active ? 'Active' : 'Inactive'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {users.length === 0 && (
                    <div className="text-center py-8 text-gray-500">No users found</div>
                  )}
                </div>
                <Pagination
                  pagination={usersPagination}
                  onPageChange={fetchUsers}
                />
              </div>
            )}

            {/* Campaigns Tab */}
            {activeTab === 'campaigns' && (
              <div className="space-y-4">
                {campaigns.map(campaign => (
                  <div key={campaign.id} className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <span className="text-white font-medium">{campaign.email}</span>
                        <span className="text-gray-500 text-sm ml-2">(User #{campaign.user_id})</span>
                      </div>
                      <div className="text-right text-sm text-gray-400">
                        <div>Schedule: {campaign.schedule_cron}</div>
                        <div>Last run: {formatRelativeDate(campaign.last_run)}</div>
                      </div>
                    </div>
                    {campaign.user_prompt && (
                      <div className="mb-3">
                        <div className="text-gray-500 text-xs uppercase mb-1">Prompt</div>
                        <div className="text-gray-300 text-sm bg-gray-800/50 p-2 rounded">
                          {campaign.user_prompt}
                        </div>
                      </div>
                    )}
                    {campaign.refined_persona && (
                      <div className="mb-3">
                        <div className="text-gray-500 text-xs uppercase mb-1">AI Persona</div>
                        <div className="text-gray-400 text-sm">{campaign.refined_persona.substring(0, 200)}...</div>
                      </div>
                    )}
                  </div>
                ))}
                {campaigns.length === 0 && (
                  <div className="text-center py-8 text-gray-500">No campaigns configured</div>
                )}
                <Pagination
                  pagination={campaignsPagination}
                  onPageChange={fetchCampaigns}
                />
              </div>
            )}

            {/* Posts Tab */}
            {activeTab === 'posts' && (
              <div className="space-y-4">
                {posts.map(post => (
                  <div key={post.id} className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <span className="text-white font-medium">{post.email}</span>
                        <span className="text-gray-500 text-sm ml-2">{formatRelativeDate(post.created_at)}</span>
                      </div>
                      <div className="flex gap-1">
                        {post.platforms?.includes('twitter') && (
                          <span className="px-2 py-0.5 text-xs bg-blue-900/50 text-blue-400 rounded flex items-center gap-1">
                            <Twitter className="w-3 h-3" /> Twitter
                          </span>
                        )}
                        {post.platforms?.includes('linkedin') && (
                          <span className="px-2 py-0.5 text-xs bg-blue-900/50 text-blue-400 rounded flex items-center gap-1">
                            <Linkedin className="w-3 h-3" /> LinkedIn
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-gray-300 text-sm whitespace-pre-wrap">{post.post_text}</div>
                    {post.topics && post.topics.length > 0 && (
                      <div className="mt-2 flex gap-1 flex-wrap">
                        {post.topics.map((topic, i) => (
                          <span key={i} className="px-2 py-0.5 text-xs bg-gray-800 text-gray-400 rounded">
                            {topic}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {posts.length === 0 && (
                  <div className="text-center py-8 text-gray-500">No posts yet</div>
                )}
                <Pagination
                  pagination={postsPagination}
                  onPageChange={fetchPosts}
                />
              </div>
            )}

            {/* Mentions Tab */}
            {activeTab === 'mentions' && (
              <div className="space-y-6">
                {/* Add New Mention Form */}
                <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
                  <h3 className="text-white font-medium mb-4 flex items-center gap-2">
                    <Plus className="w-4 h-4" /> Add LinkedIn Company Mention
                  </h3>
                  {mentionError && (
                    <div className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
                      {mentionError}
                    </div>
                  )}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <input
                      type="text"
                      placeholder="Company Name"
                      value={newMention.company_name}
                      onChange={(e) => setNewMention({ ...newMention, company_name: e.target.value })}
                      className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                    />
                    <input
                      type="text"
                      placeholder="urn:li:organization:XXXXX"
                      value={newMention.organization_urn}
                      onChange={(e) => setNewMention({ ...newMention, organization_urn: e.target.value })}
                      className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                    />
                    <input
                      type="text"
                      placeholder="Aliases (comma-separated)"
                      value={newMention.aliases}
                      onChange={(e) => setNewMention({ ...newMention, aliases: e.target.value })}
                      className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                    />
                    <button
                      onClick={createMention}
                      disabled={!newMention.company_name || !newMention.organization_urn}
                      className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Add Mention
                    </button>
                  </div>
                  <p className="mt-2 text-gray-500 text-xs">
                    Format: @[Company Name](urn:li:organization:ID) - The URN can be found on the company&apos;s LinkedIn page URL or via LinkedIn API.
                  </p>
                </div>

                {/* Mentions List */}
                <div className="bg-gray-900/50 border border-gray-800 rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-gray-800">
                        <th className="text-left px-4 py-3 text-gray-400 font-medium">Company</th>
                        <th className="text-left px-4 py-3 text-gray-400 font-medium">URN</th>
                        <th className="text-left px-4 py-3 text-gray-400 font-medium">Aliases</th>
                        <th className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
                        <th className="text-right px-4 py-3 text-gray-400 font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mentions.map(mention => (
                        <tr key={mention.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                          <td className="px-4 py-3">
                            {editingMention === mention.id ? (
                              <input
                                type="text"
                                defaultValue={mention.company_name}
                                onBlur={(e) => updateMention(mention.id, { company_name: e.target.value })}
                                className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white w-full"
                              />
                            ) : (
                              <span className="text-white font-medium">{mention.company_name}</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-gray-400 text-sm font-mono">{mention.organization_urn}</td>
                          <td className="px-4 py-3">
                            <div className="flex gap-1 flex-wrap">
                              {mention.aliases?.map((alias, i) => (
                                <span key={i} className="px-2 py-0.5 text-xs bg-gray-800 text-gray-400 rounded">
                                  {alias}
                                </span>
                              ))}
                              {(!mention.aliases || mention.aliases.length === 0) && (
                                <span className="text-gray-600 text-sm">None</span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <button
                              onClick={() => toggleMentionActive(mention)}
                              className={`px-2 py-1 text-xs rounded ${
                                mention.is_active ? 'bg-green-900/50 text-green-400' : 'bg-gray-800 text-gray-500'
                              }`}
                            >
                              {mention.is_active ? 'Active' : 'Inactive'}
                            </button>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex justify-end gap-2">
                              <button
                                onClick={() => setEditingMention(editingMention === mention.id ? null : mention.id)}
                                className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
                                title="Edit"
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => deleteMention(mention.id)}
                                className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded transition-colors"
                                title="Delete"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {mentions.length === 0 && (
                    <div className="text-center py-8 text-gray-500">No mentions configured yet</div>
                  )}
                </div>

                {/* Preview */}
                <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
                  <h3 className="text-white font-medium mb-2">Preview</h3>
                  <p className="text-gray-400 text-sm mb-3">
                    When these company names appear in LinkedIn posts, they will be automatically converted to mentions:
                  </p>
                  <div className="space-y-2">
                    {mentions.filter(m => m.is_active).map(mention => (
                      <div key={mention.id} className="text-sm">
                        <span className="text-gray-500">&quot;{mention.company_name}&quot;</span>
                        {mention.aliases?.length > 0 && (
                          <span className="text-gray-600"> or &quot;{mention.aliases.join('&quot;, &quot;')}&quot;</span>
                        )}
                        <span className="text-gray-500"> → </span>
                        <span className="text-blue-400">@[{mention.company_name}]({mention.organization_urn})</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function StatCard({ label, value, icon }: { label: string; value: number; icon?: React.ReactNode }) {
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
        {icon}
        {label}
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
    </div>
  );
}

function Pagination({ pagination, onPageChange }: { pagination: PaginationState; onPageChange: (page: number) => void }) {
  if (pagination.pages <= 1) return null;

  return (
    <div className="flex items-center justify-between">
      <div className="text-sm text-gray-400">
        {pagination.total} total
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(pagination.page - 1)}
          disabled={pagination.page <= 1}
          className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <span className="text-gray-300 text-sm">
          Page {pagination.page} of {pagination.pages}
        </span>
        <button
          onClick={() => onPageChange(pagination.page + 1)}
          disabled={pagination.page >= pagination.pages}
          className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
