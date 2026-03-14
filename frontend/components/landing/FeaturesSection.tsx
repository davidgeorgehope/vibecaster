import { Terminal, Send, ImagePlus, Megaphone, Link, Globe } from 'lucide-react';

const features = [
  {
    icon: Terminal,
    title: 'One-Line Install',
    description: 'npx skills add for 40+ AI coding agents. Works with Claude Code, Codex, Cursor, Windsurf, and more.',
  },
  {
    icon: Send,
    title: 'Direct Posting',
    description: 'Post text, images, and video to any connected platform. Your agent handles formatting and character limits.',
  },
  {
    icon: ImagePlus,
    title: 'AI Image Gen',
    description: 'Use --imagegen to generate images from prompts with Google Imagen. Attached automatically to posts.',
  },
  {
    icon: Megaphone,
    title: 'Campaign Autopilot',
    description: 'Set a prompt and schedule. Your agent generates and posts content daily — no manual intervention.',
  },
  {
    icon: Link,
    title: 'URL to Post',
    description: 'Give your agent any URL. It reads the content and creates platform-optimized posts instantly.',
  },
  {
    icon: Globe,
    title: 'Multi-Platform',
    description: 'X, LinkedIn, and YouTube from a single command. Connect accounts via OAuth in the dashboard.',
  },
];

export default function FeaturesSection() {
  return (
    <section id="features" className="py-24 px-6 scroll-mt-20">
      <div className="container mx-auto max-w-6xl">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
            Everything Your Agent{' '}
            <span className="gradient-text">Needs</span>
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto mb-8">
            A complete social media toolkit designed for AI agents — install, connect, post.
          </p>

          {/* GEO-optimized statistics */}
          <div className="flex flex-wrap justify-center gap-8 text-center">
            <div>
              <div className="text-3xl font-bold text-purple-400">40+</div>
              <div className="text-sm text-gray-500">Compatible Agents</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-purple-400">3</div>
              <div className="text-sm text-gray-500">Platforms Supported</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-purple-400">Free</div>
              <div className="text-sm text-gray-500">During Beta</div>
            </div>
          </div>
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
