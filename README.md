# Blog-to-Video Pipeline

A semi-automated AI video production pipeline that converts blog posts into scripts, voiceovers, subtitles, visuals, and rendered videos while tracking time spent at each step.

---

# Overview

This project aims to build a **semi-automated video generation workflow** using multiple AI APIs and media tools.

The pipeline transforms written blog content into:
- AI-generated narration scripts
- Scene breakdowns
- Visual assets
- Voiceovers
- Subtitles
- Fully rendered videos

The goal is **not full end-to-end automation**, but rather a practical semi-automated workflow with measurable production timings.

---

# Pipeline Flow

```txt
Blog URL / Markdown / Text
            ↓
    Article Extraction
            ↓
     Content Cleaning
            ↓
     Script Generation
            ↓
       Scene Splitting
            ↓
   Asset Prompt Generation
            ↓
 Image / Video Asset Search
            ↓
      Voice Generation
            ↓
     Subtitle Generation
            ↓
       Video Composition
            ↓
        Final Render
```

---

# Tech Stack

## LLM / Script Generation
- OpenAI GPT API
- Claude API
- Gemini API

## Voice Generation
- ElevenLabs
- OpenAI TTS

## Image Generation
- DALL·E
- Stable Diffusion
- Midjourney
- Leonardo AI

## Video Generation
- Runway
- Pika
- Luma AI
- Google Veo

## Subtitle Generation
- Whisper
- AssemblyAI

## Media Processing
- FFmpeg
- MoviePy
- Remotion

## Stock Media APIs
- Pexels API
- Unsplash API

---

# MVP Scope

The initial MVP focuses on:

- Extracting blog content
- Generating narration scripts
- Splitting scenes automatically
- Fetching relevant images/videos
- Generating AI voice narration
- Creating subtitles
- Rendering a basic video
- Logging processing time for each stage

---

# Suggested Architecture

```txt
project/
│
├── input/
│   └── article.txt
│
├── output/
│   ├── script.json
│   ├── scenes.json
│   ├── voice.mp3
│   ├── subtitles.srt
│   └── final_video.mp4
│
├── logs/
│   └── time_report.csv
│
├── src/
│   ├── extract_article.py
│   ├── generate_script.py
│   ├── split_scenes.py
│   ├── generate_assets.py
│   ├── generate_voice.py
│   ├── generate_subtitles.py
│   └── compose_video.py
│
└── README.md
```

---

# Example Workflow

## 1. Extract Blog Content
- Input:
  - Blog URL
  - Markdown file
  - Raw text

## 2. Generate Narration Script
- Convert article into:
  - Hook
  - Main narration
  - Outro / CTA

## 3. Split Into Scenes
Example:
```json
[
  {
    "scene": 1,
    "duration": 6,
    "narration": "Artificial intelligence is changing video production."
  }
]
```

## 4. Generate Assets
- AI-generated images
- Stock footage
- Background visuals

## 5. Generate Voiceover
- AI narration using TTS APIs

## 6. Generate Subtitles
- Automatic SRT generation

## 7. Compose Final Video
- Merge:
  - visuals
  - narration
  - subtitles
  - background music

---

# Time Tracking

Each stage logs execution time.

Example:

| Step | Time |
|---|---|
| Article Extraction | 12s |
| Script Generation | 35s |
| Scene Splitting | 8s |
| Asset Search | 40s |
| Voice Generation | 25s |
| Subtitle Generation | 14s |
| Final Rendering | 95s |

---

# Future Improvements

- Fully autonomous pipeline
- Multi-agent orchestration
- Auto-upload to YouTube/TikTok
- Dynamic B-roll generation
- AI avatar narration
- Emotion-aware voice synthesis
- Automatic thumbnail generation
- Real-time editing dashboard

---

# Example Output

```txt
Input:
→ Blog article

Output:
→ Narration script
→ AI voiceover
→ Scene visuals
→ Subtitles
→ Rendered MP4 video
```

---

# Status

🚧 In Development

Current focus:
- Pipeline orchestration
- API integration
- Scene automation
- Rendering workflow
- Time measurement logging

---

# Repository Goal

Build a scalable AI-powered media orchestration pipeline for transforming written content into video content efficiently.
