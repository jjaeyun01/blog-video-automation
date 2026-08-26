from __future__ import annotations

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
    if not spec.disclaimer.strip():
        errors.append("medical disclaimer is required")
    ending = spec.scenes[-1].narration if spec.scenes else ""
    if not any(word in ending.lower() for word in CONSULTATION_TERMS[language]):
        errors.append("the final scene must recommend appropriate medical consultation")
    if errors:
        raise ValueError("Medical copy review failed:\n- " + "\n- ".join(errors))
