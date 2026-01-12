import { Sparkles, Check } from 'lucide-react';

const betaFeatures = [
  'Unlimited AI post generation',
  'X (Twitter) & LinkedIn integration',
  'YouTube video uploads',
  'Video generation with Google Veo',
  'Audio/video transcription',
  'Campaign automation',
];

export default function PricingSection() {
  return (
    <section id="pricing" className="py-24 px-6 bg-gray-900/30 scroll-mt-20">
      <div className="container mx-auto max-w-4xl">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
            Simple <span className="gradient-text">Pricing</span>
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            Pricing plans coming soon. Get early access during beta.
          </p>
        </div>

        {/* Beta Card */}
        <div className="max-w-lg mx-auto">
          <div className="relative bg-gray-950 border-2 border-purple-500/50 rounded-2xl p-8 overflow-hidden">
            {/* Glow Effect */}
            <div className="absolute inset-0 bg-gradient-to-br from-purple-500/10 to-pink-500/10" />

            {/* Badge */}
            <div className="relative inline-flex items-center gap-2 px-3 py-1 bg-purple-500/20 border border-purple-500/30 rounded-full mb-6">
              <Sparkles className="w-4 h-4 text-purple-400" />
              <span className="text-sm font-medium text-purple-300">Beta Access</span>
            </div>

            {/* Price */}
            <div className="relative mb-6">
              <span className="text-5xl font-bold text-white">Free</span>
              <span className="text-gray-400 ml-2">during beta</span>
            </div>

            {/* Description */}
            <p className="relative text-gray-400 mb-8">
              Get full access to all features while we're in beta.
              Help shape the future of Vibecaster with your feedback.
            </p>

            {/* Features */}
            <ul className="relative space-y-3 mb-8">
              {betaFeatures.map((feature) => (
                <li key={feature} className="flex items-center gap-3">
                  <div className="w-5 h-5 rounded-full bg-purple-500/20 flex items-center justify-center flex-shrink-0">
                    <Check className="w-3 h-3 text-purple-400" />
                  </div>
                  <span className="text-gray-300 text-sm">{feature}</span>
                </li>
              ))}
            </ul>

            {/* CTA */}
            <a
              href="/signup"
              className="relative block w-full py-4 text-center text-lg font-semibold text-white bg-gradient-to-r from-purple-600 to-pink-600 hover:opacity-90 rounded-xl transition-opacity"
            >
              Get Beta Access
            </a>
          </div>
        </div>

        {/* Coming Soon Note */}
        <p className="text-center text-gray-500 text-sm mt-8">
          Paid plans with additional features will be available after beta.
        </p>
      </div>
    </section>
  );
}
