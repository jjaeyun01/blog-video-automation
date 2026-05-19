from __future__ import annotations

import json
import re
from pathlib import Path

from src.config.settings import Settings
from src.models import Article, JobResult, VideoScript


class Storage:
    def __init__(self, settings: Settings):
        self.settings = settings

    def job_dir(self, article: Article) -> Path:
        slug = _slugify(article.title)[:64] or article.id
        path = self.settings.output_dir / "jobs" / f"{article.id}-{slug}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_article(self, article: Article, job_dir: Path) -> Path:
        path = job_dir / "article.json"
        path.write_text(
            json.dumps(article.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def save_script(self, script: VideoScript, job_dir: Path) -> Path:
        path = job_dir / "script.json"
        path.write_text(
            json.dumps(script.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def save_scenes(self, script: VideoScript, job_dir: Path) -> Path:
        path = job_dir / "scenes.json"
        scenes = [scene.to_dict() for scene in script.scenes]
        path.write_text(
            json.dumps(scenes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def save_job_result(self, result: JobResult, job_dir: Path) -> Path:
        path = job_dir / "job_result.json"
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def _slugify(text: str) -> str:
    text = re.sub(r"^Q:\s*", "", text).strip().lower()
    text = re.sub(r"[^\w가-힣]+", "-", text)
    return text.strip("-")
