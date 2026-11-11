"""Stage human-reviewed FAIL videos without modifying the original jobs tree.

The feedback filenames are submission aliases, not canonical job names.  In
particular, week8 English item 26 corresponds to Korean/Spanish item 25.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


FEEDBACK_FILES = (
    Path("/Users/jaeyoonlee/.codex/attachments/6dae6324-39a7-401c-9d2c-5db661cb5027/pasted-text.txt"),
    Path("/Users/jaeyoonlee/.codex/attachments/d02c228f-9558-42b8-9d3a-513da01c814d/pasted-text.txt"),
)
LANGUAGES = {"Korean": "ko", "English": "en", "Spanish": "es"}
SET_SLUGS = {
    3: "infant-wheezing-pneumonia-antibiotics",
    4: "baby-40c-fever-no-other-symptoms",
    6: "pediatric-fever-sleep",
    7: "influenza-a-high-fever-management",
    8: "pediatric-tamiflu-dosing-flexibility",
}
WEEK_SLUGS = {
    10: "influenza-a-high-fever-management",
    11: "pediatric-tamiflu-dosing-flexibility",
    13: "baby-formula-refusal-cold",
    15: "baby-fever-threshold",
    18: "powdered-fever-reducer-premix",
    20: "pediatric-fever-alternating-meds",
    21: "baby-enteritis-medicine-stop",
    22: "persistent-nasal-congestion-reassessment",
    25: "infant-cold-vomiting-feeding",
    29: "mycoplasma-pneumonia-fever-reassessment",
}
SCENES = {
    "infant-wheezing-pneumonia-antibiotics": (1, 4, 6, 7, 9),
    "baby-40c-fever-no-other-symptoms": (1, 2, 5, 6, 8),
    "pediatric-fever-sleep": (3, 5, 6, 9, 10),
    "influenza-a-high-fever-management": (4, 5, 6, 8),
    "pediatric-tamiflu-dosing-flexibility": (2, 3, 5, 6, 8),
    "baby-formula-refusal-cold": (5, 6),
    "baby-fever-threshold": (2, 7, 8),
    "powdered-fever-reducer-premix": (5, 6, 8),
    "pediatric-fever-alternating-meds": (3, 4, 5, 6, 8),
    "baby-enteritis-medicine-stop": (2, 5, 6, 7, 9),
    "persistent-nasal-congestion-reassessment": (7, 8),
    "infant-cold-vomiting-feeding": (5, 6, 8, 9),
    "mycoplasma-pneumonia-fever-reassessment": (1, 5, 6, 7, 9),
}
VISUAL_FIXES = {
    "infant-wheezing-pneumonia-antibiotics": {
        9: "Show safe infant sleep: baby supine on a firm flat bare crib mattress, with no pillow, wedge, loose blanket, or raised mattress. No unsafe sleep pose.",
    },
    "baby-fever-threshold": {
        2: "Show safe infant sleep only: flat firm bare crib mattress, baby on back, no pillow or loose blanket.",
        8: "Show safe infant sleep only: flat firm bare crib mattress, baby on back, no pillow or loose blanket.",
    },
    "persistent-nasal-congestion-reassessment": {
        8: "Show age-appropriate gentle nasal saline care with the child upright and head neutral. Do not tilt the head far backward or force liquid into the nostril.",
    },
    "infant-cold-vomiting-feeding": {
        5: "Show a correctly prepared normal-strength formula bottle; do not show dilution or changing the powder-to-water ratio.",
        8: "Show a caregiver holding an infant upright with head and neck securely supported. Do not show unsupported dangling or unsafe sleep positioning.",
    },
    "pediatric-fever-alternating-meds": {
        8: "If depicting oral liquid medicine, use a clearly open-rimmed medicine cup at the lips. No syringe, plunger, needle, or injection motion near the mouth.",
    },
}
NAME = re.compile(
    r"^Jaeyoon-Lee-(?P<batch>0907-set|week8-)(?P<index>\d+)-"
    r"(?P<language>Korean|English|Spanish)(?:-v\d+)?\.mp4$"
    r"|^Jaeyoon-Lee-week8-(?P<weekly_language>Korean|English|Spanish)-"
    r"(?P<weekly_index>\d+)\.mp4$"
)


def target_for(name: str) -> tuple[str, str]:
    match = NAME.fullmatch(name)
    if not match:
        raise ValueError(f"Unrecognized FAIL filename: {name}")
    if match.group("weekly_language"):
        language = LANGUAGES[match.group("weekly_language")]
        index = int(match.group("weekly_index"))
        if language == "en" and index == 26:
            index = 25
        slug = WEEK_SLUGS[index]
    elif match.group("batch") == "0907-set":
        language = LANGUAGES[match.group("language")]
        slug = SET_SLUGS[int(match.group("index"))]
    else:
        language = LANGUAGES[match.group("language")]
        index = int(match.group("index"))
        if language == "en" and index == 26:
            index = 25
        slug = WEEK_SLUGS[index]
    return slug, language


def collect_fails() -> dict[tuple[str, str], list[dict[str, str]]]:
    targets: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for path in FEEDBACK_FILES:
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.reader(source, delimiter="\t"):
                if len(row) < 5 or row[1].strip() != "Sam" or row[4].strip() != "F":
                    continue
                slug, language = target_for(row[0].strip())
                targets[(slug, language)].append({
                    "filename": row[0].strip(),
                    "feedback_file": str(path),
                    "reason_ko": row[11].strip() if len(row) > 11 else "",
                    "additional_ko": row[12].strip() if len(row) > 12 else "",
                })
    return dict(targets)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs-dir", type=Path, default=Path("jobs"))
    parser.add_argument("--revision-dir", type=Path, default=Path("Revision"))
    args = parser.parse_args()
    failures = collect_fails()
    expected = {(slug, language) for slug in SCENES for language in ("ko", "en", "es")}
    if set(failures) != expected:
        raise RuntimeError(f"FAIL mapping mismatch; missing={expected - set(failures)}, extra={set(failures) - expected}")
    for slug in SCENES:
        source = args.jobs_dir / slug
        for language in ("ko", "en", "es"):
            if not (source / language / f"{slug}_{language.upper()}.mp4").is_file():
                raise FileNotFoundError(source / language / f"{slug}_{language.upper()}.mp4")
            if not (source / language / "production.snapshot.json").is_file():
                raise FileNotFoundError(source / language / "production.snapshot.json")
        if len(list((source / "visuals" / "clips").glob("scene_*.mp4"))) != 10:
            raise RuntimeError(f"Incomplete source clips: {slug}")

    revision = args.revision_dir
    raw_dir = revision / "feedback_audit" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    staged = revision / "work_jobs"
    staged.mkdir(parents=True, exist_ok=True)
    for slug in SCENES:
        destination = staged / slug
        if not destination.exists():
            print(f"STAGE {slug}", flush=True)
            shutil.copytree(args.jobs_dir / slug, destination)

    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "feedback_files": [str(p) for p in FEEDBACK_FILES], "topics": len(SCENES), "language_videos": len(failures), "targets": []}
    for (slug, language), records in sorted(failures.items()):
        notes = list(dict.fromkeys(" ".join((record["reason_ko"], record["additional_ko"])).strip() for record in records))
        issues = []
        for index in SCENES[slug]:
            issues.append({
                "scene": index,
                "category": "MEDICAL_ERROR",
                "severity": "high",
                "problem_ko": " / ".join(notes),
                "evidence": ", ".join(record["filename"] for record in records),
            })
            visual = VISUAL_FIXES.get(slug, {}).get(index)
            if visual:
                issues.append({
                    "scene": index,
                    "category": "OTHER_VISUAL_ERROR",
                    "severity": "high",
                    "problem_ko": "사람 검토에서 지적된 시각적 안전 오류를 제거해야 합니다.",
                    "visual_prompt_addendum": visual,
                    "evidence": ", ".join(record["filename"] for record in records),
                })
        result = {"video_id": f"{slug}.{language}", "overall_verdict": "FAIL", "reviewer": "Sam", "human_feedback": records, "issues": issues}
        (raw_dir / f"{slug}.{language}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["targets"].append({"slug": slug, "language": language, "feedback": records, "staged_video": str((staged / slug / language / f"{slug}_{language.upper()}.mp4").resolve())})
    (revision / "feedback_fail_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"READY {len(failures)} language videos across {len(SCENES)} topics; {sum(map(len, failures.values()))} FAIL feedback rows", flush=True)


if __name__ == "__main__":
    main()
