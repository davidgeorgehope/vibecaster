'use client';

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';

const faqs = [
  {
    question: 'What is Vibecaster?',
    answer: 'Vibecaster is a skill for AI coding agents (like Claude Code, Codex, and Cursor) that gives them the ability to post to X (Twitter), LinkedIn, and YouTube. Install it once with a single command, then just tell your agent what to post.',
  },
  {
    question: 'Which AI agents are supported?',
    answer: 'Vibecaster works with any agent that supports the skills protocol — over 40 agents including Claude Code, OpenAI Codex, Cursor, Windsurf, Cline, Aider, and more. You can also use the CLI directly with npx vibecaster.',
  },
  {
    question: 'How does it work?',
    answer: 'After installing the skill, your AI agent can call Vibecaster commands to generate and post content. It uses Google Gemini AI for content generation and Imagen for image creation. You connect your social accounts via OAuth in the web dashboard, and your agent handles the rest.',
  },
  {
    question: 'Which social media platforms are supported?',
    answer: 'Vibecaster supports X (Twitter), LinkedIn, and YouTube. Connect your accounts securely via OAuth in the dashboard. Your agent can post to one or all platforms with a single command.',
  },
  {
    question: 'Is Vibecaster free to use?',
    answer: 'Yes, Vibecaster is completely free during the beta period. You get full access to all features including direct posting, AI content generation, image generation, video processing, campaign automation, and transcription.',
  },
  {
    question: 'Is my data and social media accounts secure?',
    answer: 'Vibecaster uses OAuth for secure authentication with all social platforms — we never store your social media passwords. API keys are hashed server-side. You can revoke access or disconnect accounts at any time from the dashboard.',
  },
];

export default function FAQSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const faqSchema = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faqs.map((faq) => ({
      '@type': 'Question',
      name: faq.question,
      acceptedAnswer: {
        '@type': 'Answer',
        text: faq.answer,
      },
    })),
  };

  return (
    <section id="faq" className="py-24 px-6 scroll-mt-20">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }}
      />
      <div className="container mx-auto max-w-3xl">
        <div className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">
            Frequently Asked{' '}
            <span className="gradient-text">Questions</span>
          </h2>
          <p className="text-xl text-gray-400">
            Everything you need to know about Vibecaster
          </p>
        </div>

        <div className="space-y-4">
          {faqs.map((faq, index) => (
            <div
              key={index}
              className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-xl overflow-hidden"
            >
              <button
                onClick={() => setOpenIndex(openIndex === index ? null : index)}
                className="w-full px-6 py-5 text-left flex items-center justify-between gap-4 hover:bg-gray-800/30 transition-colors"
              >
                <span className="text-lg font-medium text-white">
                  {faq.question}
                </span>
                <ChevronDown
                  className={`w-5 h-5 text-gray-400 transition-transform ${
                    openIndex === index ? 'rotate-180' : ''
                  }`}
                />
              </button>
              <div
                className={`overflow-hidden transition-all duration-300 ${
                  openIndex === index ? 'max-h-96' : 'max-h-0'
                }`}
              >
                <p className="px-6 pb-5 text-gray-400 leading-relaxed">
                  {faq.answer}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
