from __future__ import annotations

from pathlib import Path

from src.ai.safety_reviewer import SafetyReviewer
from src.models import Article, JobResult


class BlogVideoPipeline:
    def __init__(
        self,
        discovery,
        extractor,
        cleaner,
        script_generator,
        scene_generator,
        tts_provider,
        subtitle_generator,
        renderer,
        storage,
        time_tracker,
        safety_reviewer: SafetyReviewer,
    ):
        self.discovery = discovery
        self.extractor = extractor
        self.cleaner = cleaner
        self.script_generator = script_generator
        self.scene_generator = scene_generator
        self.tts_provider = tts_provider
        self.subtitle_generator = subtitle_generator
        self.renderer = renderer
        self.storage = storage
        self.time_tracker = time_tracker
        self.safety_reviewer = safety_reviewer

    def run_from_source(self, source_url: str, limit: int = 5) -> list[JobResult]:
        with self.time_tracker.step("post_discovery"):
            posts = self.discovery.discover(source_url, limit=limit)

        results = []
        for post in posts:
            with self.time_tracker.step("article_extraction"):
                article = self.extractor.extract(post)
            results.append(self._run_article(article))

        return results

    def run_from_file(self, path: Path) -> JobResult:
        with self.time_tracker.step("article_file_load"):
            article = self.extractor.extract_file(path)
        return self._run_article(article)

    def _run_article(self, article: Article) -> JobResult:
        job_dir = self.storage.job_dir(article)

        with self.time_tracker.step("content_cleaning"):
            article = self.cleaner.clean(article)

        with self.time_tracker.step("script_generation"):
            script = self.script_generator.generate(article)

        with self.time_tracker.step("scene_generation"):
            script.scenes = self.scene_generator.generate(article, script)

        with self.time_tracker.step("safety_review"):
            warnings = self.safety_reviewer.review(script)
            if warnings:
                (job_dir / "safety_warnings.txt").write_text(
                    "\n".join(warnings),
                    encoding="utf-8",
                )

        with self.time_tracker.step("storage_article_script"):
            article_path = self.storage.save_article(article, job_dir)
            script_path = self.storage.save_script(script, job_dir)
            scenes_path = self.storage.save_scenes(script, job_dir)

        with self.time_tracker.step("voice_generation"):
            voice_path = self.tts_provider.generate(script, job_dir)

        with self.time_tracker.step("subtitle_generation"):
            subtitles_path = self.subtitle_generator.generate(script, job_dir)

        with self.time_tracker.step("video_render"):
            render_manifest_path, final_video_path = self.renderer.render(
                article,
                script,
                voice_path,
                subtitles_path,
                job_dir,
            )

        result = JobResult(
            job_id=job_dir.name,
            article_path=article_path,
            script_path=script_path,
            scenes_path=scenes_path,
            voice_path=voice_path,
            subtitles_path=subtitles_path,
            render_manifest_path=render_manifest_path,
            final_video_path=final_video_path,
        )
        self.storage.save_job_result(result, job_dir)
        return result
