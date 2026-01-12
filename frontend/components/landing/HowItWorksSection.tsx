import { Link2, Settings, Zap } from 'lucide-react';

const steps = [
  {
    number: '01',
    icon: Link2,
    title: 'Connect',
    description: 'Link your X (Twitter), LinkedIn, and YouTube accounts securely via OAuth. Your credentials stay safe.',
  },
  {
    number: '02',
    icon: Settings,
    title: 'Configure',
    description: 'Set your content prompt and preferences. Our AI analyzes your style and creates a unique persona.',
  },
  {
    number: '03',
    icon: Zap,
    title: 'Automate',
    description: 'Sit back as AI generates and posts content daily using Google Gemini & Imagen. Stay consistent effortlessly.',
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
            Get started in minutes. No complex setup required.
          </p>
        </div>

        {/* Steps */}
        <div className="relative">
          {/* Connecting Line */}
          <div className="hidden md:block absolute top-1/2 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-500/0 via-purple-500/50 to-purple-500/0 -translate-y-1/2" />

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12">
            {steps.map((step, index) => (
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
                  <p className="text-gray-400 text-sm leading-relaxed">
                    {step.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
