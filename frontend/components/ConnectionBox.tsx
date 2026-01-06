'use client';

import { useState } from 'react';
import { CheckCircle, XCircle, Loader2 } from 'lucide-react';

interface ConnectionBoxProps {
  service: 'twitter' | 'linkedin' | 'youtube';
  connected: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}

const SERVICE_CONFIG = {
  twitter: { name: 'X (Twitter)', color: 'from-blue-500 to-blue-700' },
  linkedin: { name: 'LinkedIn', color: 'from-blue-600 to-blue-800' },
  youtube: { name: 'YouTube', color: 'from-red-500 to-red-700' }
};

export default function ConnectionBox({
  service,
  connected,
  onConnect,
  onDisconnect
}: ConnectionBoxProps) {
  const [isLoading, setIsLoading] = useState(false);

  const serviceName = SERVICE_CONFIG[service].name;
  const serviceColor = SERVICE_CONFIG[service].color;

  const handleAction = async () => {
    setIsLoading(true);
    try {
      if (connected) {
        await onDisconnect();
      } else {
        await onConnect();
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-lg p-6 hover:border-gray-700 transition-all">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-semibold text-white">{serviceName}</h3>
        {connected ? (
          <CheckCircle className="w-6 h-6 text-green-500" />
        ) : (
          <XCircle className="w-6 h-6 text-gray-500" />
        )}
      </div>

      <div className="mb-4">
        <div className="flex items-center space-x-2">
          <div className={`h-2 w-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-gray-600'}`}></div>
          <span className="text-sm text-gray-400">
            {connected ? 'Connected' : 'Not Connected'}
          </span>
        </div>
      </div>

      <button
        onClick={handleAction}
        disabled={isLoading}
        className={`w-full py-3 px-4 rounded-lg font-medium transition-all ${
          connected
            ? 'bg-red-600 hover:bg-red-700 text-white'
            : `bg-gradient-to-r ${serviceColor} hover:opacity-90 text-white neon-glow`
        } disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center`}
      >
        {isLoading ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : connected ? (
          'Disconnect'
        ) : (
          'Connect'
        )}
      </button>
    </div>
  );
}
