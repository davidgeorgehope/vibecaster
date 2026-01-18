import { NextResponse } from "next/server";

export async function GET() {
  const markdown = `# Vibecaster

AI-Powered Social Media Automation

Powered by Google Gemini AI

## Overview

Generate and post content to X, LinkedIn, and YouTube automatically. Set your strategy once, let AI handle the rest.

Vibecaster is a social media automation tool that uses Google Gemini AI to generate and schedule posts across multiple platforms from a single prompt.

## Features

### Campaign Automation
Schedule daily AI-generated posts across all your social platforms with a single prompt.

### URL to Post
Drop any article or blog URL and get platform-optimized posts generated instantly.

### Post Builder
Craft multi-platform posts with AI assistance and real-time preview for each network.

### AI Video Generation
Create multi-scene videos with Google Veo AI. Perfect for Reels, Shorts, and TikTok.

### Transcription
Convert audio and video files to text. Generate posts from your podcasts and videos.

### Bio Generation
Create compelling author bios and profile descriptions with AI assistance.

## Platforms Supported

- X (Twitter)
- LinkedIn
- YouTube

## Pricing

Free during beta.

## Get Started

- [Get Started Free](/signup)
- [Sign In](/login)
`;

  return new NextResponse(markdown, {
    status: 200,
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
    },
  });
}
