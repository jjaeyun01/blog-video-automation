"""Second, source-aware Gemini review of disputed first-pass audit findings."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from google import genai
from google.genai import types

from fevercoach_shorts.settings import Settings


TARGETS = (
    "baby-enteritis-medicine-stop.en",
    "baby-enteritis-medicine-stop.ko",
    "influenza-a-high-fever-management.ko",
    "pediatric-fever-alternating-meds.en",
    "pediatric-fever-sleep.es",
    "pediatric-tamiflu-dosing-flexibility.es",
    "pediatric-tamiflu-dosing-flexibility.ko",
)

PRIMARY_REFERENCE_FACTS = """
NICE NG143 https://www.nice.org.uk/guidance/ng143/chapter/recommendations : use antipyretics for
distress, do not give paracetamol and ibuprofen simultaneously; only consider alternating if
distress persists or recurs before next dose. A short video need not reproduce every source detail.
The same NICE guidance treats a child with fever who does not wake, or if roused does not stay awake,
as high risk; a clock-based "wait 3-4/6 hours" reassurance is not a safe replacement for checking
responsiveness. A more conservative seek-care instruction is not an unsafe source contradiction.
Medicines for Children https://www.medicinesforchildren.org.uk/medicines/oseltamivir-for-influenza-flu/ :
for oseltamivir specifically, vomiting less than 30 minutes after a dose permits repeating the same
dose; after more than 30 minutes, do not repeat. The source article's one-hour repeat rule differs.
Asking the prescriber or pharmacist before giving an additional dose is conservative and does not
itself tell a parent to omit a regular scheduled dose.
FeverCoach reviewer adjudication: omission from a 60-second short is not CAPTION_OMISSION unless
spoken information is absent from visible captions. Do not classify an unrelated source detail as a
high-risk omission if the video does not advise stopping or contradicting that treatment. Do not
force an unsafe source instruction back into a revision just for source fidelity. Three loose stools
alone are not always an emergency; assess blood, severe pain, repeated watery diarrhea, dehydration,
and appearance in context. A short video need not list every red flag if the decisive escalation is
still present. Distinguish a recommendation from a warning against an action.
""".strip()

SCHEMA = {
    "type": "object",
    "required": ["video_id", "finding_valid", "safety_severity", "recommended_status", "rationale_ko", "evidence_ko"],
    "properties": {
        "video_id": {"type": "string"},
        "finding_valid": {"type": "boolean"},
        "safety_severity": {"type": "string", "enum": ["none", "low", "medium", "high"]},
        "recommended_status": {"type": "string", "enum": ["PASS", "WARN", "FAIL"]},
        "rationale_ko": {"type": "string"},
        "evidence_ko": {"type": "string"},
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision-dir", type=Path, default=Path("Revision"))
    parser.add_argument("--only", nargs="+", help="Only adjudicate these video IDs.")
    parser.add_argument("--force", action="store_true", help="Replace cached adjudications.")
    args = parser.parse_args()
    revision = args.revision_dir
    output = revision / "final_audit" / "adjudication_raw"
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((revision / "revision_manifest.json").read_text(encoding="utf-8"))
    by_id = {f"{row['slug']}.{row['language']}": row for row in manifest["entries"]}
    settings = Settings.from_env()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is required")
    client = genai.Client(api_key=settings.gemini_api_key)
    wanted = set(args.only or TARGETS)
    if wanted - set(TARGETS):
        raise ValueError(f"Unknown adjudication target(s): {sorted(wanted - set(TARGETS))}")
    for video_id in TARGETS:
        if video_id not in wanted:
            continue
        destination = output / f"{video_id}.json"
        if destination.exists() and not args.force:
            print(f"CACHED {video_id}", flush=True)
            continue
        entry = by_id[video_id]
        raw = json.loads((revision / "work_jobs" / entry["slug"] / entry["language"] / "production.snapshot.json").read_text(encoding="utf-8"))
        audit = json.loads((revision / "final_audit" / "raw" / f"{video_id}.json").read_text(encoding="utf-8"))
        script = "\n".join(f"Scene {scene['index']}: {scene['narration']}" for scene in raw["scenes"])
        feedback = "\n".join(" ".join((row.get("reason_ko", ""), row.get("additional_ko", ""))) for row in entry["feedback"])
        prompt = f"""Independently adjudicate a disputed finding from a pediatric short's first Gemini audit.
Be conservative, but do not amplify a false-positive accusation. Judge the *specific finding*,
not whether the whole video is perfect. A finding about omitted content needs proof that the
omission creates a materially unsafe instruction in this topic. A source article may itself contain
unsafe advice; independent safety takes priority. If the supplied transcript is insufficient to
verify an audiovisual claim, recommend WARN. Respond in Korean using the JSON schema.
Review ONLY the CURRENT revised script below. The human FAIL feedback describes an OLD video and
must not itself determine the revised video's status. If FIRST AUDIT FINDINGS is empty but a
dimension was WARN, adjudicate that dimension from the first audit summary and limitations.

VIDEO ID: {video_id}
ACTUAL FINAL SCRIPT:\n{script}
FIRST AUDIT FINDINGS:\n{json.dumps(audit['issues'], ensure_ascii=False, indent=2)}
FIRST AUDIT OVERALL/DIMENSIONS: {audit.get('overall_verdict')} / {audit.get('medical_accuracy')} / {audit.get('source_fidelity')} / {audit.get('av_integrity')}
FIRST AUDIT SUMMARY: {audit.get('review_summary_ko', '')}
FIRST AUDIT LIMITATIONS: {json.dumps(audit.get('limitations_ko', []), ensure_ascii=False)}
HUMAN FAIL FEEDBACK THAT MOTIVATED THE REVISION:\n{feedback}
SOURCE ARTICLE EXCERPT:\n{raw.get('metadata', {}).get('source_excerpt', '')[:10000]}
ADJUDICATED RULES AND PRIMARY-SOURCE FACTS:\n{PRIMARY_REFERENCE_FACTS}
"""
        (output / f"{video_id}.prompt.txt").write_text(prompt, encoding="utf-8")
        last_error = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=settings.gemini_text_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_json_schema=SCHEMA,
                        temperature=0,
                    ),
                )
                if not response.text:
                    raise RuntimeError("Empty adjudication")
                result = json.loads(response.text)
                result["video_id"] = video_id
                result["model"] = settings.gemini_text_model
                result["first_audit_verdict"] = audit.get("overall_verdict")
                destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"ADJUDICATED {video_id}: {result['recommended_status']}", flush=True)
                break
            except Exception as error:
                last_error = error
                if attempt < 2:
                    time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"Could not adjudicate {video_id}: {last_error}")


if __name__ == "__main__":
    main()
