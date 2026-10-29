export default function JsonLd() {
  const organizationSchema = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'Vibecaster',
    url: 'https://vibecaster.app',
    logo: 'https://vibecaster.app/og-image.png',
    description: 'AI-powered social media automation platform that generates and posts content to X (Twitter), LinkedIn, and YouTube.',
    sameAs: [],
  };

  const websiteSchema = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'Vibecaster',
    url: 'https://vibecaster.app',
    description: 'Automate your social media with AI. Generate and post content to X, LinkedIn, and YouTube using xAI Grok.',
    potentialAction: {
      '@type': 'SearchAction',
      target: {
        '@type': 'EntryPoint',
        urlTemplate: 'https://vibecaster.app/search?q={search_term_string}',
      },
      'query-input': 'required name=search_term_string',
    },
  };

  const softwareAppSchema = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'Vibecaster',
    applicationCategory: 'BusinessApplication',
    operatingSystem: 'Web',
    url: 'https://vibecaster.app',
    description: 'Vibecaster is an AI-powered social media automation platform that uses xAI Grok to generate and automatically post content to X (Twitter), LinkedIn, and YouTube.',
    offers: {
      '@type': 'Offer',
      price: '0',
      priceCurrency: 'USD',
      description: 'Free during beta',
    },
    featureList: [
      'AI content generation with xAI Grok',
      'Auto-posting to X (Twitter)',
      'Auto-posting to LinkedIn',
      'Auto-posting to YouTube',
      'AI video generation with Grok Imagine Video',
      'Audio transcription',
      'Campaign automation',
    ],
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationSchema) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteSchema) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareAppSchema) }}
      />
    </>
  );
}
