from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .models import ProductionSpec
from .providers.assets import SceneAssetGenerator
from .providers.character import CharacterReferenceGenerator
from .providers.prompt_refiner import VeoPromptRefiner
from .providers.tts import build_timeline_audio, create_tts_provider
from .providers.video_audit import (
    FinalVideoAuditor,
    actionable_issues,
    apply_repairs,
    find_duplicate_owner,
    register_final_video,
)
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
        if tts_provider != "gemini":
            raise ValueError(
                "FeverCoach narration is locked to the canonical Gemini/Kore voice profile."
            )
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

        spec = CharacterReferenceGenerator(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_image_model,
        ).generate(spec, visual_dir)
        assets = SceneAssetGenerator(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_image_model,
        )
        refiner = VeoPromptRefiner(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_text_model,
        )
        for reference_round in range(self.settings.gemini_audit_max_repair_rounds + 1):
            spec = assets.generate(spec, visual_dir)
            try:
                spec = refiner.refine(spec, visual_dir)
                break
            except RuntimeError as error:
                if ("reference image has a high medical safety risk" not in str(error)
                        or reference_round >= self.settings.gemini_audit_max_repair_rounds):
                    raise
                spec, changed = repair_reference_prompts(spec, visual_dir, reference_round + 1)
                if not changed:
                    raise
                print(f"Reference safety repair {reference_round + 1}: regenerate scenes {sorted(changed)}", flush=True)
        write_generation_plan(spec, self.settings.gemini_video_model, visual_dir)

        veo = VeoGenerator(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_video_model,
            fallback_model=self.settings.gemini_video_fallback_model,
            poll_interval_seconds=self.settings.veo_poll_interval_sec,
        )
        clips = veo.generate(spec, visual_dir)
        if clips_only:
            return visual_dir / "operations.json"

        renderer = ShortsRenderer()
        output = self._render(spec, clips, tts_provider, renderer, job_dir)
        auditor = FinalVideoAuditor(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_audit_model,
            min_confidence=self.settings.gemini_audit_min_confidence,
        )
        audit_dir = job_dir / "audit"
        source_text = str(spec.metadata.get("source_excerpt", "")).strip()
        if not source_text:
            source_text = (
                "The original article text was not embedded in this legacy production. "
                "Use the source-grounded medical_facts and scene claims below."
            )

        maximum_audits = self.settings.gemini_audit_max_repair_rounds + 1
        for audit_round in range(1, maximum_audits + 1):
            duplicate_owner = find_duplicate_owner(
                self.settings.jobs_dir / ".final_video_registry.json", spec, output
            )
            if duplicate_owner:
                raise RuntimeError(
                    f"Final video duplicates a different registered production: "
                    f"{duplicate_owner}. The file is blocked before review submission."
                )
            result = auditor.audit(spec, output, audit_dir, audit_round, source_text)
            issues = actionable_issues(
                result, self.settings.gemini_audit_min_confidence
            )
            if not issues:
                if result.get("overall_verdict") == "FAIL":
                    raise RuntimeError(
                        f"Gemini final medical audit failed without a safe automatic repair. "
                        f"Review {audit_dir / f'round_{audit_round:02}.json'}"
                    )
                (audit_dir / "final_report.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                register_final_video(
                    self.settings.jobs_dir / ".final_video_registry.json", spec, output
                )
                return output

            if audit_round >= maximum_audits:
                scenes = sorted({int(issue["scene"]) for issue in issues})
                raise RuntimeError(
                    f"Gemini medical audit still requires repairs in scenes {scenes} after "
                    f"{self.settings.gemini_audit_max_repair_rounds} automatic rounds. "
                    f"Review {audit_dir / f'round_{audit_round:02}.json'}"
                )

            spec, changed_scenes = apply_repairs(spec, issues, audit_round)
            if not changed_scenes:
                raise RuntimeError(
                    f"Gemini found an error but supplied no safe scene repair. Review "
                    f"{audit_dir / f'round_{audit_round:02}.json'}"
                )
            validate_medical_copy(spec)
            spec.save(audit_dir / f"repaired_round_{audit_round:02}.production.json")
            print(
                f"Gemini audit round {audit_round}: regenerating only scenes "
                f"{sorted(changed_scenes)}"
            )
            clips = veo.generate(spec, visual_dir)
            output = self._render(spec, clips, tts_provider, renderer, job_dir)

        raise RuntimeError("Final medical audit ended unexpectedly.")

    def _render(
        self,
        spec: ProductionSpec,
        clips: list[Path],
        tts_provider: str,
        renderer: ShortsRenderer,
        job_dir: Path,
    ) -> Path:
        provider = create_tts_provider(tts_provider, self.settings, spec.language)
        narration = build_timeline_audio(spec, provider, job_dir)
        subtitles = write_srt(spec, job_dir / "subtitles.srt")
        return renderer.render(spec, clips, narration, subtitles, job_dir)


def repair_reference_prompts(spec: ProductionSpec, visual_dir: Path, round_index: int) -> tuple[ProductionSpec, set[int]]:
    """Recreate flagged source images; never conceal an unsafe first frame with motion."""
    manifest = json.loads((visual_dir / "refined_prompts.json").read_text(encoding="utf-8"))
    changed = set()
    scenes = []
    for scene in spec.scenes:
        flags = manifest.get("scenes", {}).get(str(scene.index), {}).get("risk_flags", [])
        risks = [flag for flag in flags if isinstance(flag, dict)
                 and flag.get("severity") == "high"
                 and flag.get("type") in {"medical_ambiguity", "generated_text"}]
        if not risks or not scene.asset_prompt:
            scenes.append(scene)
            continue
        reasons = "; ".join(str(flag.get("reason", "")) for flag in risks)
        correction = (
            f"\nREFERENCE IMAGE SAFETY CORRECTION {round_index}: {reasons}. "
            "Create a new safe starting frame faithful to the source-grounded scene claim. "
            "All surfaces, age markers, packaging and displays must be completely blank. "
            "No visible letters, digits, units, writing or numeric age markers, even if mentioned "
            "in the earlier description. Numeric meaning is added later by code. "
            "Keep medication route, age-appropriate posture and anatomy safe; do not invent "
            "a new treatment, diagnosis, dose or outcome."
        )
        scenes.append(replace(scene, image=None, asset_prompt=scene.asset_prompt + correction))
        changed.add(scene.index)
    return replace(spec, scenes=scenes), changed


def read_status(config_path: Path, settings: Settings) -> dict:
    spec = ProductionSpec.load(config_path, check_files=False)
    base = settings.jobs_dir / spec.slug
    path = (base / "visuals" if spec.metadata.get("multilingual") else base) / "operations.json"
    if not path.exists():
        return {"slug": spec.slug, "status": "NOT_STARTED", "scenes": {}}
    return json.loads(path.read_text(encoding="utf-8"))
