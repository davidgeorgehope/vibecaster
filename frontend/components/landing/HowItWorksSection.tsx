import { Terminal, Link2, MessageSquare } from 'lucide-react';

const steps = [
  {
    number: '01',
    icon: Terminal,
    title: 'Install',
    description: 'Run npx skills add davidgeorgehope/vibecaster in your terminal. Works with any AI coding agent that supports skills.',
    code: 'npx skills add davidgeorgehope/vibecaster',
  },
  {
    number: '02',
    icon: Link2,
    title: 'Connect',
    description: 'Link your X, LinkedIn, and YouTube accounts via OAuth in the dashboard. Create an API key for your agent.',
    code: null,
  },
  {
    number: '03',
    icon: MessageSquare,
    title: 'Post',
    description: 'Tell your agent "Post to LinkedIn about..." — it generates the content, formats it for each platform, and posts.',
    code: '"Post to LinkedIn: Just shipped v2.0 with 3x faster builds"',
  },
];

export default function HowItWorksSection() {
  return (
    <section id="how-it-works" className="py-24 px-6 bg-gray-900/30 scroll-mt-20">
      <div className="container mx-auto max-w-5xl">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
            How It <span className="gradient-text">Works</span>
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            Three steps. One minute to install. Then your agent handles the rest.
          </p>
        </div>

        {/* Steps */}
        <div className="relative">
          {/* Connecting Line */}
          <div className="hidden md:block absolute top-1/2 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-500/0 via-purple-500/50 to-purple-500/0 -translate-y-1/2" />

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12">
            {steps.map((step) => (
              <div key={step.number} className="relative">
                {/* Step Card */}
                <div className="bg-gray-950 border border-gray-800 rounded-xl p-8 text-center hover:border-purple-500/50 transition-colors">
                  {/* Number Badge */}
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 px-4 py-1 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full">
                    <span className="text-sm font-bold text-white">{step.number}</span>
                  </div>

                  {/* Icon */}
                  <div className="w-16 h-16 mx-auto rounded-full bg-gray-800 flex items-center justify-center mb-6 mt-2">
                    <step.icon className="w-8 h-8 text-purple-400" />
                  </div>

                  {/* Content */}
                  <h3 className="text-2xl font-semibold text-white mb-3">
                    {step.title}
                  </h3>
                  <p className="text-gray-400 text-sm leading-relaxed mb-4">
                    {step.description}
                  </p>

                  {/* Code snippet */}
                  {step.code && (
                    <div className="bg-gray-900/80 rounded-lg px-3 py-2 font-mono text-xs text-purple-300 text-left overflow-x-auto">
                      {step.code}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
