from __future__ import annotations

import json
from pathlib import Path

from .models import ProductionSpec
from .providers.assets import SceneAssetGenerator
from .providers.tts import build_timeline_audio, create_tts_provider
from .providers.veo import VeoGenerator, write_generation_plan
from .renderer import ShortsRenderer
from .safety import validate_medical_copy
from .settings import Settings
from .subtitles import write_srt


class ShortsPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build(
        self,
        config_path: Path,
        tts_provider: str = "gemini",
        plan_only: bool = False,
        clips_only: bool = False,
    ) -> Path:
        spec = ProductionSpec.load(config_path, check_files=not plan_only)
        validate_medical_copy(spec)
        multilingual = bool(spec.metadata.get("multilingual"))
        job_root = self.settings.jobs_dir / spec.slug
        job_dir = job_root / spec.language if multilingual else job_root
        visual_dir = job_root / "visuals" if multilingual else job_dir
        job_dir.mkdir(parents=True, exist_ok=True)
        visual_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "production.snapshot.json").write_text(
            json.dumps(spec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if plan_only:
            return write_generation_plan(spec, self.settings.gemini_video_model, visual_dir)
        if not self.settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for video generation.")

        spec = SceneAssetGenerator(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_image_model,
        ).generate(spec, visual_dir)
        write_generation_plan(spec, self.settings.gemini_video_model, visual_dir)

        clips = VeoGenerator(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_video_model,
            fallback_model=self.settings.gemini_video_fallback_model,
            poll_interval_seconds=self.settings.veo_poll_interval_sec,
        ).generate(spec, visual_dir)
        if clips_only:
            return visual_dir / "operations.json"

        provider = create_tts_provider(tts_provider, self.settings, spec.language)
        narration = build_timeline_audio(spec, provider, job_dir)
        subtitles = write_srt(spec, job_dir / "subtitles.srt")
        return ShortsRenderer().render(spec, clips, narration, subtitles, job_dir)


def read_status(config_path: Path, settings: Settings) -> dict:
    spec = ProductionSpec.load(config_path, check_files=False)
    base = settings.jobs_dir / spec.slug
    path = (base / "visuals" if spec.metadata.get("multilingual") else base) / "operations.json"
    if not path.exists():
        return {"slug": spec.slug, "status": "NOT_STARTED", "scenes": {}}
    return json.loads(path.read_text(encoding="utf-8"))
