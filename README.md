# FeverCoach Blog Video Automation

Pipeline scaffold for turning FeverCoach blog posts into short-form video assets.

The first version is intentionally runnable without paid API keys. It can:

- discover Korean blog posts from the FeverCoach RSS feed
- load a local article text file
- clean article text
- generate a source-faithful short video script
- split the script into scenes
- generate subtitle files
- write a render manifest and time report

Generated audio/video are dry-run placeholders until a real TTS and renderer are plugged in.

## Quick Start

Use the included local sample article and render a real MP4 locally:

```bash
python3 -m src.cli --input-file fevercoach_post.txt --limit 1
```

Discover posts from the FeverCoach Korean RSS feed:

```bash
python3 -m src.cli --source https://www.fevercoach.us/ko/blog --limit 3
```

Outputs are written to `output/jobs/<job_id>/`, including `final_video.mp4`.

## Recommended Production Flow

The default path is fully local:

1. Python creates article/script/scenes/subtitles.
2. macOS `say` creates `voice.aiff`.
3. FFmpeg renders `final_video.mp4`.

The higher-quality production path is:

1. Python pipeline creates article/script/scenes/subtitles/audio/render manifest.
2. OpenAI writes a natural Korean short-form script and creates `voice.mp3`.
3. FFmpeg renders the final vertical MP4, or Remotion renders a more customizable template.

Run the full production-prep pipeline:

```bash
python3 -m src.cli \
  --input-file fevercoach_post.txt \
  --script-provider openai \
  --tts-provider openai \
  --renderer ffmpeg
```

This generates:

```txt
output/jobs/<job_id>/
  article.json
  script.json
  scenes.json
  voice.mp3
  subtitles.srt
  render_manifest.json
  final_video.mp4
```

Use Remotion only when you want a more advanced motion template:

```bash
python3 -m src.cli --input-file fevercoach_post.txt --renderer remotion
cd remotion
npm install
npx remotion render src/Root.tsx BlogVideo ../output/jobs/<job_id>/final_video.mp4 --props public/jobs/<job_id>/manifest.json
```

The exact Remotion render command is also written to each job's `render_command.txt`.

## Environment

Copy `.env.example` to `.env` if you want to add real providers later.

```bash
OPENAI_API_KEY=
ELEVENLABS_API_KEY=
```

For OpenAI-backed generation:

```bash
OPENAI_API_KEY=sk-...
OPENAI_TEXT_MODEL=gpt-4o-mini
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=alloy
```

## Architecture

```txt
Discovery -> Extraction -> Cleaning -> Script -> Scenes -> Voice -> Subtitles -> Render Manifest
```

Core modules:

- `src/extractors`: RSS discovery, file/URL article extraction, text cleanup
- `src/ai`: script and scene generation, safety checks
- `src/media`: TTS placeholder, SRT generation, render manifest
- `src/pipeline`: orchestration, storage, time tracking

## Safety

Medical content is handled as informational content only. The generated script keeps a disclaimer and avoids adding diagnosis, dosage, or treatment instructions that are not present in the source article.
