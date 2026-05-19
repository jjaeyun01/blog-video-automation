from __future__ import annotations

import csv
import time
from contextlib import contextmanager
from pathlib import Path


class TimeTracker:
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    @contextmanager
    def step(self, name: str):
        started = time.perf_counter()
        try:
            yield
            status = "ok"
        except Exception:
            status = "error"
            raise
        finally:
            elapsed = time.perf_counter() - started
            self.rows.append(
                {
                    "step": name,
                    "seconds": f"{elapsed:.3f}",
                    "status": status,
                }
            )

    def flush(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["step", "seconds", "status"])
            writer.writeheader()
            writer.writerows(self.rows)
