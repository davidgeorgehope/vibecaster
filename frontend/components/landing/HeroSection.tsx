import Link from 'next/link';
import { ArrowRight, Sparkles } from 'lucide-react';

export default function HeroSection() {
  return (
    <section className="min-h-screen flex items-center justify-center pt-20 pb-16 px-6">
      <div className="container mx-auto max-w-5xl text-center">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-purple-500/10 border border-purple-500/20 rounded-full mb-8">
          <Sparkles className="w-4 h-4 text-purple-400" />
          <span className="text-sm text-purple-300">Powered by Google Gemini AI</span>
        </div>

        {/* Headline */}
        <h1 className="text-5xl md:text-7xl font-bold text-white mb-6 leading-tight">
          AI-Powered{' '}
          <span className="gradient-text">Social Media</span>{' '}
          Automation
        </h1>

        {/* Subheadline */}
        <p className="text-xl md:text-2xl text-gray-400 mb-6 max-w-3xl mx-auto leading-relaxed">
          Generate and post content to X, LinkedIn, and YouTube automatically.
          Set your strategy once, let AI handle the rest.
        </p>

        {/* GEO-optimized quotable definition */}
        <p className="text-base text-gray-500 mb-10 max-w-2xl mx-auto italic">
          Vibecaster is a social media automation tool that uses Google Gemini AI to generate and schedule posts across multiple platforms from a single prompt.
        </p>

        {/* CTA Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link
            href="/signup"
            className="group px-8 py-4 text-lg font-semibold text-white bg-gradient-to-r from-purple-600 to-pink-600 hover:opacity-90 rounded-xl transition-all flex items-center gap-2"
          >
            Get Started Free
            <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </Link>
          <a
            href="#how-it-works"
            className="px-8 py-4 text-lg font-semibold text-gray-300 hover:text-white border border-gray-700 hover:border-gray-600 rounded-xl transition-colors"
          >
            See How It Works
          </a>
        </div>

        {/* Social Proof */}
        <div className="mt-16 flex flex-wrap items-center justify-center gap-8 text-gray-500">
          <div className="flex items-center gap-2">
            <div className="flex -space-x-2">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500" />
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-cyan-500" />
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-green-500 to-emerald-500" />
            </div>
            <span className="text-sm">Join creators automating their presence</span>
          </div>
        </div>
      </div>
    </section>
  );
}
