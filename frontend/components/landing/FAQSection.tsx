'use client';

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';

const faqs = [
  {
    question: 'What is Vibecaster?',
    answer: 'Vibecaster is an AI-powered social media automation platform that generates and posts content to X (Twitter), LinkedIn, and YouTube using Google Gemini and Imagen. It allows creators and businesses to maintain a consistent social media presence without manual daily posting.',
  },
  {
    question: 'How does AI content generation work?',
    answer: 'Vibecaster uses Google Gemini AI to analyze your brand voice and generate platform-optimized posts. You set your content strategy and tone once through a simple prompt, and AI creates unique posts tailored to each platform\'s best practices and character limits.',
  },
  {
    question: 'Which social media platforms are supported?',
    answer: 'Vibecaster supports X (Twitter), LinkedIn, and YouTube. Connect your accounts securely via OAuth authentication and post to all platforms simultaneously or individually. We never store your social media passwords.',
  },
  {
    question: 'Is Vibecaster free to use?',
    answer: 'Yes, Vibecaster is completely free during the beta period. You get full access to all features including AI post generation, video creation with Google Veo, audio transcription, and campaign automation at no cost.',
  },
  {
    question: 'How do I get started with Vibecaster?',
    answer: 'Getting started takes less than 5 minutes: Sign up for a free account, connect your social media accounts via OAuth, set your content prompt describing your brand voice and topics, and Vibecaster will automatically generate and post content based on your schedule.',
  },
  {
    question: 'Is my data and social media accounts secure?',
    answer: 'Vibecaster uses OAuth for secure authentication with all social platforms. We never store your social media passwords. Your credentials and data are protected with industry-standard encryption, and you can disconnect your accounts at any time.',
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
