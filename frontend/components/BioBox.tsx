'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { User, Upload, Sparkles, Search, Loader2, Check, AlertCircle, Trash2, Image, Download } from 'lucide-react';

interface BioBoxProps {
  token: string | null;
  showNotification: (type: 'success' | 'error' | 'info', message: string) => void;
}

interface AuthorBio {
  exists: boolean;
  name: string;
  description: string;
  style: string;
  has_reference_image: boolean;
  reference_image_base64?: string;
  reference_image_mime?: string;
}

interface SearchResult {
  url: string;
  title: string;
  description?: string;
  source?: string;
}

const STYLE_OPTIONS = [
  { value: 'real_person', label: 'Real Person', description: 'Photorealistic portrait' },
  { value: 'cartoon', label: 'Cartoon', description: 'Colorful cartoon style' },
  { value: 'anime', label: 'Anime', description: 'Japanese anime style' },
  { value: 'avatar', label: 'Avatar', description: '3D stylized avatar' },
  { value: '3d_render', label: '3D Render', description: 'Cinematic 3D rendering' },
];

export default function BioBox({ token, showNotification }: BioBoxProps) {
  const [bio, setBio] = useState<AuthorBio>({
    exists: false,
    name: '',
    description: '',
    style: 'real_person',
    has_reference_image: false
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const [isDownloading, setIsDownloading] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadBio = useCallback(async () => {
    if (!token) return;

    try {
      const response = await fetch('/api/author-bio', {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setBio(data);
      }
    } catch (error) {
      console.error('Failed to load bio:', error);
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  // Load bio on mount
  useEffect(() => {
    if (token) {
      loadBio();
    }
  }, [token, loadBio]);

  const handleSave = async () => {
    if (!token) return;

    setIsSaving(true);
    try {
      const response = await fetch('/api/author-bio', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: bio.name,
          description: bio.description,
          style: bio.style
        })
      });

      if (response.ok) {
        showNotification('success', 'Author bio saved');
        setBio(prev => ({ ...prev, exists: true }));
      } else {
        const error = await response.json();
        showNotification('error', error.detail || 'Failed to save bio');
      }
    } catch (error) {
      showNotification('error', 'Failed to save bio');
    } finally {
      setIsSaving(false);
    }
  };

  const handleGenerateReference = async () => {
    if (!token || !bio.description.trim()) {
      showNotification('error', 'Please enter a description first');
      return;
    }

    setIsGenerating(true);
    try {
      const response = await fetch('/api/author-bio/generate-reference', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          description: bio.description,
          style: bio.style,
          additional_context: bio.name ? `This character's name is ${bio.name}` : ''
        })
      });

      if (response.ok) {
        const data = await response.json();
        setBio(prev => ({
          ...prev,
          has_reference_image: true,
          reference_image_base64: data.image_base64,
          reference_image_mime: data.mime_type
        }));
        showNotification('success', 'Character reference generated!');
      } else {
        const error = await response.json();
        showNotification('error', error.detail || 'Failed to generate image');
      }
    } catch (error) {
      showNotification('error', 'Failed to generate image');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSearch = async () => {
    if (!token || !searchQuery.trim()) {
      showNotification('error', 'Please enter a search query');
      return;
    }

    setIsSearching(true);
    setShowSearchResults(true);
    try {
      const response = await fetch('/api/author-bio/search-images', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          author_name: searchQuery,
          limit: 6
        })
      });

      if (response.ok) {
        const data = await response.json();
        setSearchResults(data.results || []);
        if (data.results?.length === 0) {
          showNotification('info', 'No images found');
        }
      } else {
        showNotification('error', 'Search failed');
        setSearchResults([]);
      }
    } catch (error) {
      showNotification('error', 'Search failed');
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleDownloadImage = async (url: string) => {
    if (!token) return;

    setIsDownloading(url);
    try {
      const response = await fetch('/api/author-bio/download-image', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ url })
      });

      if (response.ok) {
        const data = await response.json();
        setBio(prev => ({
          ...prev,
          has_reference_image: true,
          reference_image_base64: data.image_base64,
          reference_image_mime: data.mime_type
        }));
        setShowSearchResults(false);
        showNotification('success', 'Image set as reference!');
      } else {
        const error = await response.json();
        showNotification('error', error.detail || 'Failed to download image');
      }
    } catch (error) {
      showNotification('error', 'Failed to download image');
    } finally {
      setIsDownloading(null);
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!token) return;

    // Validate file
    if (!file.type.startsWith('image/')) {
      showNotification('error', 'Please select an image file');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      showNotification('error', 'Image too large. Maximum: 10MB');
      return;
    }

    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/author-bio/upload-reference', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        setBio(prev => ({
          ...prev,
          has_reference_image: true,
          reference_image_base64: data.image_base64,
          reference_image_mime: data.mime_type
        }));
        showNotification('success', 'Image uploaded!');
      } else {
        const error = await response.json();
        showNotification('error', error.detail || 'Failed to upload image');
      }
    } catch (error) {
      showNotification('error', 'Failed to upload image');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileUpload(file);
  };

  const handleDelete = async () => {
    if (!token) return;

    if (!confirm('Are you sure you want to delete your author bio?')) return;

    try {
      const response = await fetch('/api/author-bio', {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        setBio({
          exists: false,
          name: '',
          description: '',
          style: 'real_person',
          has_reference_image: false
        });
        showNotification('success', 'Author bio deleted');
      } else {
        showNotification('error', 'Failed to delete bio');
      }
    } catch (error) {
      showNotification('error', 'Failed to delete bio');
    }
  };

  if (isLoading) {
    return (
      <div className="bg-gray-900/50 backdrop-blur-sm rounded-xl border border-gray-800 p-8">
        <div className="flex items-center justify-center">
          <Loader2 className="w-6 h-6 animate-spin text-purple-400" />
          <span className="ml-2 text-gray-400">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900/50 backdrop-blur-sm rounded-xl border border-gray-800 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
            <User className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">Author Bio</h2>
            <p className="text-sm text-gray-400">Your character reference for video generation</p>
          </div>
        </div>
        {bio.exists && (
          <button
            onClick={handleDelete}
            className="p-2 text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
            title="Delete bio"
          >
            <Trash2 className="w-5 h-5" />
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: Form */}
        <div className="space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Name</label>
            <input
              type="text"
              value={bio.name}
              onChange={(e) => setBio(prev => ({ ...prev, name: e.target.value }))}
              placeholder="e.g., Alex, Dr. Smith, Captain Video"
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Description</label>
            <textarea
              value={bio.description}
              onChange={(e) => setBio(prev => ({ ...prev, description: e.target.value }))}
              placeholder="Describe the character's appearance: age, gender, hair color, distinctive features, typical attire..."
              rows={4}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
            />
          </div>

          {/* Style */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Visual Style</label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {STYLE_OPTIONS.map((style) => (
                <button
                  key={style.value}
                  onClick={() => setBio(prev => ({ ...prev, style: style.value }))}
                  className={`p-3 rounded-lg border text-left transition-all ${
                    bio.style === style.value
                      ? 'border-purple-500 bg-purple-500/20 text-white'
                      : 'border-gray-700 bg-gray-800/50 text-gray-300 hover:border-gray-600'
                  }`}
                >
                  <div className="font-medium text-sm">{style.label}</div>
                  <div className="text-xs text-gray-400 mt-0.5">{style.description}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Save Button */}
          <button
            onClick={handleSave}
            disabled={isSaving || !bio.name.trim() || !bio.description.trim()}
            className="w-full py-2.5 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                Save Bio
              </>
            )}
          </button>
        </div>

        {/* Right Column: Reference Image */}
        <div className="space-y-4">
          {/* Current Reference Image */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Reference Image</label>

            {bio.has_reference_image && bio.reference_image_base64 ? (
              <div className="relative group">
                <img
                  src={`data:${bio.reference_image_mime || 'image/png'};base64,${bio.reference_image_base64}`}
                  alt="Reference"
                  className="w-full max-h-64 object-contain rounded-lg border border-gray-700 bg-gray-800"
                />
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center">
                  <span className="text-white text-sm">Click below to change</span>
                </div>
              </div>
            ) : (
              <div
                onDrop={handleDrop}
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onClick={() => fileInputRef.current?.click()}
                className={`w-full h-48 border-2 border-dashed rounded-lg flex flex-col items-center justify-center cursor-pointer transition-colors ${
                  isDragging
                    ? 'border-purple-500 bg-purple-500/10'
                    : 'border-gray-700 hover:border-gray-600 bg-gray-800/30'
                }`}
              >
                {isUploading ? (
                  <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
                ) : (
                  <>
                    <Image className="w-8 h-8 text-gray-500 mb-2" />
                    <p className="text-sm text-gray-400">Drop image or click to upload</p>
                    <p className="text-xs text-gray-500 mt-1">PNG, JPG, WEBP up to 10MB</p>
                  </>
                )}
              </div>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileUpload(file);
              }}
              className="hidden"
            />
          </div>

          {/* Action Buttons */}
          <div className="space-y-2">
            {/* Generate from Description */}
            <button
              onClick={handleGenerateReference}
              disabled={isGenerating || !bio.description.trim()}
              className="w-full py-2.5 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 disabled:from-gray-700 disabled:to-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-all flex items-center justify-center gap-2"
            >
              {isGenerating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  Generate from Description
                </>
              )}
            </button>

            {/* Upload Button (if image exists) */}
            {bio.has_reference_image && (
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                className="w-full py-2.5 bg-gray-700 hover:bg-gray-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {isUploading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4" />
                    Upload New Image
                  </>
                )}
              </button>
            )}
          </div>

          {/* Search Section */}
          <div className="pt-4 border-t border-gray-700">
            <label className="block text-sm font-medium text-gray-300 mb-2">Search Online</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search for author photos..."
                className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
              <button
                onClick={handleSearch}
                disabled={isSearching || !searchQuery.trim()}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:cursor-not-allowed text-white rounded-lg transition-colors flex items-center gap-2"
              >
                {isSearching ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Search className="w-4 h-4" />
                )}
              </button>
            </div>

            {/* Search Results */}
            {showSearchResults && searchResults.length > 0 && (
              <div className="mt-3 p-3 bg-gray-800/50 rounded-lg border border-gray-700">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-400">{searchResults.length} results</span>
                  <button
                    onClick={() => setShowSearchResults(false)}
                    className="text-xs text-gray-500 hover:text-gray-400"
                  >
                    Close
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {searchResults.map((result, index) => (
                    <button
                      key={index}
                      onClick={() => handleDownloadImage(result.url)}
                      disabled={isDownloading === result.url}
                      className="relative group aspect-square bg-gray-900 rounded-lg overflow-hidden border border-gray-700 hover:border-purple-500 transition-colors"
                      title={result.title}
                    >
                      {isDownloading === result.url ? (
                        <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                          <Loader2 className="w-5 h-5 text-purple-400 animate-spin" />
                        </div>
                      ) : (
                        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                          <Download className="w-5 h-5 text-white" />
                        </div>
                      )}
                      <div className="w-full h-full flex items-center justify-center text-gray-500">
                        <Image className="w-6 h-6" />
                      </div>
                      <div className="absolute bottom-0 left-0 right-0 p-1 bg-gradient-to-t from-black/80 to-transparent">
                        <p className="text-xs text-white truncate">{result.title || result.source || 'Image'}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Info Box */}
      <div className="mt-6 p-4 bg-purple-500/10 border border-purple-500/30 rounded-lg">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-purple-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-gray-300">
            <p className="font-medium text-purple-300 mb-1">About Reference Images</p>
            <p>
              Your reference image will be used to maintain character consistency across all generated videos.
              For best results, use a clear, well-lit portrait with the face visible.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
