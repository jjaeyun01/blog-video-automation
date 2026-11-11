from __future__ import annotations

import re

from .models import ProductionSpec


BLOCKED_PHRASES = {
    "ko": ("약을 중단하세요", "복용을 중단하세요", "항생제를 끊으세요", "확실합니다", "진단됩니다", "병원에 가지 않아도"),
    "es": ("suspenda el medicamento", "deje de tomar", "deje los antibióticos", "es seguro", "se diagnostica", "no necesita ir al médico"),
    "en": ("stop the medication", "stop taking", "stop the antibiotics", "it is certain", "is diagnosed", "do not need to see a doctor"),
}

CONSULTATION_TERMS = {
    "ko": ("상담", "진료", "의사", "전문의", "소아청소년과", "병원", "의료기관"),
    "es": (
        "consulte", "consulta", "pediatra", "médico", "atención médica",
        "hospital", "clínica",
    ),
    "en": (
        "consult",
        "pediatrician",
        "doctor",
        "medical care",
        "medical advice",
        "medical attention",
        "seek care",
        "hospital",
        "clinic",
    ),
}


def validate_medical_copy(spec: ProductionSpec) -> None:
    errors: list[str] = []
    combined = " ".join(scene.narration for scene in spec.scenes)
    language = spec.language if spec.language in BLOCKED_PHRASES else "ko"
    normalized = combined.lower()
    for phrase in BLOCKED_PHRASES[language]:
        if phrase.lower() in normalized:
            errors.append(f"unsafe or overly certain phrase: {phrase}")
    for scene in spec.scenes:
        errors.extend(
            f"scene {scene.index}: {problem}"
            for problem in _clear_unsafe_instruction_errors(
                scene.narration, scene.prompt, scene.asset_prompt
            )
        )
    if not spec.disclaimer.strip():
        errors.append("medical disclaimer is required")
    ending = spec.scenes[-1].narration if spec.scenes else ""
    if not any(word in ending.lower() for word in CONSULTATION_TERMS[language]):
        errors.append("the final scene must recommend appropriate medical consultation")
    if errors:
        raise ValueError("Medical copy review failed:\n- " + "\n- ".join(errors))


def _clear_unsafe_instruction_errors(
    narration: str, visual_prompt: str, asset_prompt: str
) -> list[str]:
    """Catch the unambiguous Week 8 instructions before media generation.

    Complex clinical meaning remains with Gemini and medical reviewers; this guard only
    rejects positive instructions matching the observed unsafe wording and staging.
    """
    spoken = " ".join(narration.casefold().split())
    visuals = " ".join((visual_prompt + " " + asset_prompt).casefold().split())
    problems: list[str] = []
    # These are scoped to a sentence to preserve quoted questions or warnings elsewhere.
    sentences = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s*", spoken)
    for sentence in sentences:
        warning = bool(re.search(
            r"하지\s*마|안\s*됩|피하|금지|권하지|not\s+(?:give|use|wait|repeat)|"
            r"do\s+not|never|avoid|no\s+(?:debe|dar|esperar)|evit",
            sentence,
        ))
        if warning:
            continue
        if re.search(r"어른보다\s*한\s*겹\s*적게|one\s+layer\s+less\s+than\s+(?:an?\s+)?adult|"
                     r"una\s+capa\s+menos\s+que\s+(?:un\s+)?adult", sentence):
            problems.append("a universal 'one layer less than an adult' infant clothing rule is unsupported")
        if (re.search(r"(?:수유|분유|모유)\s*거부.{0,25}12\s*시간|"
                      r"(?:refus|not\s+feed|no\s+feed|rechaz).{0,35}12\s*(?:hours?|horas?)", sentence)
                and re.search(r"진료|병원|seek\s+care|consult|atenci[oó]n|m[eé]dico", sentence)
                and not re.search(r"더\s*일찍|그\s*전|바로|earlier|sooner|before|antes|de\s+inmediato", sentence)):
            problems.append("do not make 12 hours of feed refusal a universal minimum before care")
        if (re.search(r"분유.{0,18}(?:2\s*/\s*3|3분의\s*2|삼분의\s*이)|"
                      r"(?:formula|f[oó]rmula).{0,28}(?:two\s*thirds|2\s*/\s*3|dos\s+tercios)", sentence)
                and not re.search(r"1회|한\s*번|수유량|먹이는\s*양|per\s+feed|feeding\s+(?:amount|volume)|"
                                  r"cantidad\s+por\s+toma|por\s+toma|normal\s+concentration|정상\s*농도", sentence)):
            problems.append("specify a smaller per-feed amount, never an ambiguous formula concentration change")
        if (re.search(r"(?:가루|분말|powder|polvo).{0,80}(?:1\s*[-~–]\s*2\s*시간|"
                      r"1\s*[-~–]\s*2\s*hours?|1\s*[-~–]\s*2\s*horas?)", sentence)
                and re.search(r"냉장|refrigerat|refrigerar|frigor[ií]fico", sentence)
                and not re.search(r"제품|설명서|약사|label|product|pharmacist|etiqueta|farmac[eé]ut", sentence)):
            problems.append("powdered medicine has no universal premix/refrigeration rule")
        if (re.search(r"(?:1\s*시간|one\s+hour|1\s*hour|una\s+hora).{0,60}(?:토|구토|vomit|v[oó]mit)|"
                      r"(?:토|구토|vomit|v[oó]mit).{0,60}(?:1\s*시간|one\s+hour|1\s*hour|una\s+hora)", sentence)
                and re.search(r"다시\s*(?:먹|복용)|재투여|repeat\s+(?:the\s+)?(?:dose|medicine)|"
                                  r"give\s+(?:the\s+)?(?:full\s+)?dose\s+again|repetir\s+(?:la\s+)?dosis", sentence)
                and not re.search(r"약사|의사|설명서|prescri|pharmacist|farmac[eé]ut", sentence)):
            problems.append("do not repeat a full dose after vomiting within one hour without drug-specific instructions")
    if (re.search(r"(?:nasal\s+(?:rinse|irrigat)|sinus\s+rinse|코\s*세척|비강\s*세척|"
                  r"lavado\s+nasal|irrigaci[oó]n\s+nasal)", visuals)
            and re.search(r"(?:supine|lying\s+(?:on\s+(?:the\s+)?back|flat)|head\s+tilted\s+back|"
                          r"누워|뒤로\s*젖힌|boca\s+arriba|cabeza\s+hacia\s+atr[aá]s)", visuals)
            and not re.search(r"(?:never|avoid|no\s+|하지\s*마|금지|instead|대신)", visuals)):
        problems.append("never demonstrate nasal irrigation with a bottle while lying flat/head tilted back")
    return problems
