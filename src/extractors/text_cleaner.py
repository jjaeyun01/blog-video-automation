from __future__ import annotations

import re

from src.models import Article


class TextCleaner:
    REMOVE_LINES = {
        "top of page",
        "bottom of page",
        "FeverCoach",
    }

    def clean(self, article: Article) -> Article:
        lines = []
        has_qa_markers = "질문:" in article.raw_text and "답변:" in article.raw_text
        qa_started = not has_qa_markers

        for line in article.raw_text.splitlines():
            stripped = re.sub(r"\s+", " ", line).strip()
            if not stripped:
                continue
            if has_qa_markers and not qa_started:
                if stripped.startswith("질문:"):
                    qa_started = True
                else:
                    continue
            if stripped in self.REMOVE_LINES:
                continue
            if stripped.startswith("©"):
                continue
            lines.append(stripped)

        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        article.cleaned_text = text.strip()
        return article
