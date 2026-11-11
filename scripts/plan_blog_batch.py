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
    parser.add_argument("--languages", nargs="+", choices=["ko", "en", "es"])
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    languages = tuple(args.languages or manifest.get("languages", ["ko", "en", "es"]))
    character_value = manifest.get("character_image")
    character = Path(character_value) if character_value else None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    planner = ScenePlanner(Settings.from_env())

    failures: list[str] = []
    all_posts = manifest["posts"]
    start = max(1, args.start_index)
    end = args.end_index if args.end_index is not None else len(all_posts)
    if end < start or start > len(all_posts):
        raise SystemExit(
            f"Invalid post range {start}..{end}; manifest contains {len(all_posts)} posts."
        )
    posts = all_posts[start - 1 : min(end, len(all_posts))]
    for index, post in enumerate(posts, start=start):
        base = args.output_dir / f"{post['key']}.production.json"
        outputs = [base.with_name(f"{base.stem}.{language}{base.suffix}") for language in languages]
        if not args.force and _valid_outputs(outputs):
            print(f"SKIP {index}/{len(all_posts)} {post['key']}", flush=True)
            continue
        print(f"PLANNING {index}/{len(all_posts)} {post['key']}", flush=True)
        try:
            article = load_article(url=post["url"])
            planner.create_multilingual(article, character, base, languages)
            print(f"DONE {index}/{len(all_posts)} {post['key']}", flush=True)
        except Exception as error:  # continue so one model response does not lose the batch
            failures.append(f"{post['key']}: {error}")
            print(f"FAILED {index}/{len(all_posts)} {post['key']}: {error}", flush=True)

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
