import { Megaphone, Link, MessageSquare, Video, Mic, User } from 'lucide-react';

const features = [
  {
    icon: Megaphone,
    title: 'Campaign Automation',
    description: 'Schedule daily AI-generated posts across all your social platforms with a single prompt.',
  },
  {
    icon: Link,
    title: 'URL to Post',
    description: 'Drop any article or blog URL and get platform-optimized posts generated instantly.',
  },
  {
    icon: MessageSquare,
    title: 'Post Builder',
    description: 'Craft multi-platform posts with AI assistance and real-time preview for each network.',
  },
  {
    icon: Video,
    title: 'AI Video Generation',
    description: 'Create multi-scene videos with Google Veo AI. Perfect for Reels, Shorts, and TikTok.',
  },
  {
    icon: Mic,
    title: 'Transcription',
    description: 'Convert audio and video files to text. Generate posts from your podcasts and videos.',
  },
  {
    icon: User,
    title: 'Bio Generation',
    description: 'Create compelling author bios and profile descriptions with AI assistance.',
  },
];

export default function FeaturesSection() {
  return (
    <section id="features" className="py-24 px-6 scroll-mt-20">
      <div className="container mx-auto max-w-6xl">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
            Everything You Need to{' '}
            <span className="gradient-text">Automate</span>
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            Powerful tools to generate, schedule, and post content across all major social platforms.
          </p>
        </div>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature) => (
            <div
              key={feature.title}
              className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-xl p-6 hover:border-gray-700 transition-all group"
            >
              <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                <feature.icon className="w-6 h-6 text-white" />
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">
                {feature.title}
              </h3>
              <p className="text-gray-400 text-sm leading-relaxed">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
