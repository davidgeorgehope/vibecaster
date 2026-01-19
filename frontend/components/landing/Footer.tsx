import Link from 'next/link';
import { Zap } from 'lucide-react';

export default function Footer() {
  return (
    <footer className="border-t border-gray-800 bg-gray-950">
      <div className="container mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Brand */}
          <div className="md:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-4">
              <Zap className="w-6 h-6 text-purple-500" />
              <span className="text-xl font-bold gradient-text">VIBECASTER</span>
            </Link>
            <p className="text-gray-500 text-sm">
              AI-powered social media automation for creators and businesses.
            </p>
          </div>

          {/* Product */}
          <div>
            <h4 className="text-white font-semibold mb-4">Product</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a href="#features" className="text-gray-400 hover:text-white transition-colors">
                  Features
                </a>
              </li>
              <li>
                <a href="#how-it-works" className="text-gray-400 hover:text-white transition-colors">
                  How It Works
                </a>
              </li>
              <li>
                <a href="#pricing" className="text-gray-400 hover:text-white transition-colors">
                  Pricing
                </a>
              </li>
              <li>
                <Link href="/dashboard" className="text-gray-400 hover:text-white transition-colors">
                  Dashboard
                </Link>
              </li>
            </ul>
          </div>

          {/* Resources */}
          <div>
            <h4 className="text-white font-semibold mb-4">Resources</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <span className="text-gray-500 cursor-not-allowed">Documentation</span>
              </li>
              <li>
                <span className="text-gray-500 cursor-not-allowed">API Reference</span>
              </li>
              <li>
                <span className="text-gray-500 cursor-not-allowed">Blog</span>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h4 className="text-white font-semibold mb-4">Legal</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <span className="text-gray-500 cursor-not-allowed">Privacy Policy</span>
              </li>
              <li>
                <span className="text-gray-500 cursor-not-allowed">Terms of Service</span>
              </li>
            </ul>
            <h4 className="text-white font-semibold mb-2 mt-6">Contact</h4>
            <a href="mailto:me@davidgeorgehope.com" className="text-gray-400 hover:text-white transition-colors text-sm">
              me@davidgeorgehope.com
            </a>
          </div>
        </div>

        {/* Bottom */}
        <div className="mt-12 pt-8 border-t border-gray-800 flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-gray-500 text-sm">
            &copy; {new Date().getFullYear()} Vibecaster. All rights reserved.
          </p>
          <p className="text-gray-500 text-sm">
            Powered by Google Gemini AI & Imagen
          </p>
        </div>
      </div>
    </footer>
  );
}
