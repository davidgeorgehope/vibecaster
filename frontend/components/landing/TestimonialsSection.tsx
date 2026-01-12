import { Quote } from 'lucide-react';

const testimonials = [
  {
    quote: "Vibecaster has completely transformed how I manage my social presence. I save hours every week.",
    name: "Alex Chen",
    title: "Content Creator",
    avatar: "from-purple-500 to-pink-500",
  },
  {
    quote: "The AI-generated content is surprisingly good. My engagement has increased significantly since I started using it.",
    name: "Sarah Miller",
    title: "Marketing Manager",
    avatar: "from-blue-500 to-cyan-500",
  },
  {
    quote: "Finally, a tool that understands my brand voice. The video generation feature is a game-changer.",
    name: "Jordan Lee",
    title: "Startup Founder",
    avatar: "from-green-500 to-emerald-500",
  },
];

export default function TestimonialsSection() {
  return (
    <section className="py-24 px-6">
      <div className="container mx-auto max-w-6xl">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
            Loved by <span className="gradient-text">Creators</span>
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            See what our users have to say about Vibecaster.
          </p>
        </div>

        {/* Testimonials Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {testimonials.map((testimonial) => (
            <div
              key={testimonial.name}
              className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-xl p-6 hover:border-gray-700 transition-all"
            >
              {/* Quote Icon */}
              <Quote className="w-8 h-8 text-purple-500/50 mb-4" />

              {/* Quote Text */}
              <p className="text-gray-300 mb-6 leading-relaxed">
                "{testimonial.quote}"
              </p>

              {/* Author */}
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${testimonial.avatar}`} />
                <div>
                  <p className="text-white font-medium">{testimonial.name}</p>
                  <p className="text-gray-500 text-sm">{testimonial.title}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
