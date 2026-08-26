from __future__ import annotations

import argparse
import json
from pathlib import Path

from fevercoach_shorts.article import load_article
from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.planner import ScenePlanner
from fevercoach_shorts.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan a multilingual FeverCoach blog batch.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    languages = tuple(manifest.get("languages", ["ko", "en", "es"]))
    character = Path(manifest["character_image"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    planner = ScenePlanner(Settings.from_env())

    failures: list[str] = []
    posts = manifest["posts"]
    for index, post in enumerate(posts, start=1):
        base = args.output_dir / f"{post['key']}.production.json"
        outputs = [base.with_name(f"{base.stem}.{language}{base.suffix}") for language in languages]
        if not args.force and _valid_outputs(outputs):
            print(f"SKIP {index}/{len(posts)} {post['key']}", flush=True)
            continue
        print(f"PLANNING {index}/{len(posts)} {post['key']}", flush=True)
        try:
            article = load_article(url=post["url"])
            planner.create_multilingual(article, character, base, languages)
            print(f"DONE {index}/{len(posts)} {post['key']}", flush=True)
        except Exception as error:  # continue so one model response does not lose the batch
            failures.append(f"{post['key']}: {error}")
            print(f"FAILED {index}/{len(posts)} {post['key']}: {error}", flush=True)

    if failures:
        raise SystemExit("Batch planning failures:\n- " + "\n- ".join(failures))


def _valid_outputs(paths: list[Path]) -> bool:
    if not all(path.exists() for path in paths):
        return False
    try:
        return all(ProductionSpec.load(path).duration_seconds == 60 for path in paths)
    except (ValueError, OSError, json.JSONDecodeError):
        return False


if __name__ == "__main__":
    main()
