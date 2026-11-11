#!/usr/bin/env python3
"""Clinically faithful concise copy for 9/24 scenes that cannot fit 60 seconds."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "9" / "24" / "configs"

OVERRIDES = {
    ("mycoplasma-cough-relapse-runny-nose-reinfection", "en"): [
        "Mycoplasma cough may last 2 to 4 weeks, even after antibiotics begin.",
        "Mycoplasma inflames the airways and can cause persistent cough.",
        "Short-term reinfection is uncommon because immunity may last several months.",
        "Worsening cough with a new runny nose may mean another viral infection.",
        "Symptoms may improve and then worsen during recovery.",
        "Without red flags, recheck in 2 to 3 days; seek earlier care if symptoms worsen.",
        "Offer water often, keep humidity at 40% to 60%, and elevate the head during sleep.",
        "For children over age 1, a teaspoon of honey before bed may ease cough.",
        "Urgent signs include fast breathing, blue lips, no urine for 8 hours, fever above 38.5°C, or sleepless cough.",
        "See a pediatrician if symptoms worsen or recovery stalls.",
    ],
    ("mycoplasma-cough-relapse-runny-nose-reinfection", "es"): [
        "La tos por Micoplasma puede durar de 2 a 4 semanas, aun después de iniciar antibióticos.",
        "El Micoplasma inflama las vías respiratorias y puede causar tos persistente.",
        "La reinfección inmediata es poco común porque la inmunidad puede durar varios meses.",
        "Tos peor con nueva secreción nasal puede indicar otra infección viral.",
        "Durante la recuperación, los síntomas pueden mejorar y luego empeorar.",
        "Sin señales de alarma, reevalúe en 2 a 3 días; consulte antes si empeora.",
        "Ofrezca agua, mantenga humedad de 40% a 60% y eleve la cabeza al dormir.",
        "En mayores de 1 año, una cucharadita de miel antes de dormir puede aliviar la tos.",
        "Son urgentes la respiración rápida, labios azules, 8 horas sin orinar, fiebre sobre 38.5°C o tos sin dormir.",
        "Consulte al pediatra si los síntomas empeoran o la recuperación se detiene.",
    ],
    ("infant-vulvar-vitiligo-causes-associated-conditions", "es"): [
        "El vitíligo causa manchas blancas cuando se pierde el pigmento de la piel.",
        "Puede aparecer en cualquier zona, incluida la vulva.",
        "Su causa no se conoce por completo y no suele ser peligrosa.",
        "A menudo interviene una reacción autoinmune contra los melanocitos.",
        "También pueden influir genes y factores ambientales.",
        "Puede acompañarse de sequedad o picazón en la zona.",
        "Proteja las zonas sensibles y evite irritantes.",
        "La hidratación regular puede aliviar la sequedad.",
        "Los cambios visibles pueden afectar el ánimo; ofrezca apoyo.",
        "Consulte a pediatría o dermatología para confirmar el diagnóstico y orientar el manejo.",
    ],
    ("mycoplasma-post-treatment-dizziness", "es"): [
        "Tras la neumonía, un mareo leve puede durar una a dos semanas.",
        "La neumonía por micoplasma afecta principalmente los pulmones.",
        "Las complicaciones neurológicas graves son raras y suelen causar otros síntomas.",
        "El mareo puede deberse a rinitis, fatiga o aumento brusco de actividad.",
        "Suele mejorar gradualmente durante la recuperación.",
        "Si el mareo persiste o empeora, necesita evaluación médica.",
        "Trate la rinitis, hidrate, ofrezca hierro y levántese despacio.",
        "Anote cuándo aparece el mareo para informar al médico.",
        "Vaya al hospital por dificultad al caminar, vómitos, alteración de conciencia o fiebre recurrente.",
        "Si dura más de dos semanas o empeora, consulte al pediatra.",
    ],
}

SCENE_OVERRIDES = {
    ("child-yellow-postnasal-drip-sinusitis-reassessment", "es", 5): (
        "Los lavados nasales con solución salina, 3 a 4 veces al día, ayudan a diluir el moco."
    ),
    ("child-yellow-postnasal-drip-sinusitis-reassessment", "es", 6): (
        "Mantenga la humedad entre 40 y 60 por ciento y ofrezca líquidos tibios."
    ),
    ("child-yellow-postnasal-drip-sinusitis-reassessment", "es", 9): (
        "Consulte por fiebre sobre 38.5°C por más de 3 días, dolor facial, cefalea o dificultad respiratoria."
    ),
    ("two-month-vaccine-fever-emergency", "ko", 4): (
        "해열제는 열 반응과 불편함을 줄입니다."
    ),
    ("two-month-vaccine-fever-emergency", "en", 4): (
        "Antipyretics reduce fever-related discomfort."
    ),
    ("two-month-vaccine-fever-emergency", "es", 4): (
        "Los antipiréticos reducen el malestar por fiebre."
    ),
    ("two-month-vaccine-fever-emergency", "es", 2): (
        "La fiebre es común después de las vacunas."
    ),
    ("40c-fever-antipyretic-tepid-compress", "ko", 1): (
        "억지로 식히면 몸이 떨며 열을 더 만들고 아이를 힘들게 합니다."
    ),
    ("40c-fever-antipyretic-tepid-compress", "en", 1): (
        "Forced cooling can trigger shivering, more heat, and distress."
    ),
    ("40c-fever-antipyretic-tepid-compress", "es", 1): (
        "Enfriar a la fuerza causa temblores, más calor y malestar."
    ),
    ("40c-fever-antipyretic-tepid-compress", "ko", 3): (
        "미온수 찜질은 열을 내리지 못하고 아이를 더 힘들게 합니다."
    ),
    ("40c-fever-antipyretic-tepid-compress", "en", 3): (
        "Lukewarm compresses do not lower fever and may worsen discomfort."
    ),
    ("40c-fever-antipyretic-tepid-compress", "es", 3): (
        "Las compresas tibias no bajan la fiebre y aumentan el malestar."
    ),
    ("two-month-vaccine-fever-emergency", "ko", 7): (
        "열이 48시간 넘거나 수유가 절반 이하로 줄면 진료받고, 8시간 소변이 없으면 즉시 응급실로 가세요."
    ),
    ("two-month-vaccine-fever-emergency", "en", 7): (
        "Seek care if fever lasts over 48 hours or feeding falls by half; no urine for 8 hours needs emergency care."
    ),
    ("two-month-vaccine-fever-emergency", "es", 7): (
        "Consulte si la fiebre dura más de 48 horas o come la mitad; 8 horas sin orinar requiere urgencias."
    ),
    ("two-month-vaccine-fever-emergency", "ko", 8): (
        "5.4kg 아기에서 160mg/5mL 아세트아미노펜은 1회 1.7~2.5mL, 4~6시간 간격, 하루 최대 5회입니다."
    ),
    ("two-month-vaccine-fever-emergency", "en", 8): (
        "For a 5.4kg infant, acetaminophen 160mg per 5mL is 1.7 to 2.5mL every 4 to 6 hours, at most 5 times daily."
    ),
    ("two-month-vaccine-fever-emergency", "es", 8): (
        "Para un bebé de 5.4kg, acetaminofén 160mg por 5mL: 1.7 a 2.5mL cada 4 a 6 horas, máximo 5 veces al día."
    ),
    ("infant-pneumonia-contagious-sibling-incubation", "ko", 7): (
        "38도 이상 열·기침·숨참·처짐은 경고 신호이며, 3개월 미만의 38도 이상 열은 즉시 진료받으세요."
    ),
    ("infant-pneumonia-contagious-sibling-incubation", "en", 7): (
        "Fever at 38°C or higher with cough, breathlessness, or lethargy is concerning; under 3 months, 38°C needs immediate care."
    ),
    ("infant-pneumonia-contagious-sibling-incubation", "es", 7): (
        "Fiebre desde 38°C con tos, falta de aire o letargo es preocupante; en menores de 3 meses requiere atención inmediata."
    ),
    ("child-yellow-postnasal-drip-sinusitis-reassessment", "ko", 7): (
        "집에서 관리해도 누런 콧물이 3~4일 계속되면 소아과에 문의하세요."
    ),
    ("child-yellow-postnasal-drip-sinusitis-reassessment", "en", 7): (
        "If yellow discharge persists 3 to 4 days despite home care, contact your pediatrician."
    ),
    ("child-yellow-postnasal-drip-sinusitis-reassessment", "es", 7): (
        "Si el moco persiste 3 a 4 días con cuidados en casa, consulte a su pediatra."
    ),
    ("40c-fever-antipyretic-tepid-compress", "ko", 2): (
        "40도 고열도 가능하지만, 3개월 미만 38도·3~6개월 39도부터 즉시 진료받으세요."
    ),
    ("40c-fever-antipyretic-tepid-compress", "en", 2): (
        "A fever may reach 40°C, but seek immediate care from 38°C under 3 months or 39°C at 3 to 6 months."
    ),
    ("40c-fever-antipyretic-tepid-compress", "es", 2): (
        "40°C: menores de 3 meses, urgencias desde 38°C; de 3 a 6 meses, desde 39°C."
    ),
    ("40c-fever-antipyretic-tepid-compress", "ko", 4): (
        "교차 복용은 한 약이 전혀 듣지 않을 때만, 2~3시간 간격과 각 약의 하루 최대 횟수를 지키세요."
    ),
    ("40c-fever-antipyretic-tepid-compress", "en", 4): (
        "Alternate medicines only if one fails completely; keep 2 to 3 hours between different drugs and obey each daily maximum."
    ),
    ("40c-fever-antipyretic-tepid-compress", "es", 4): (
        "Alterne fármacos solo si uno no funciona; separe medicamentos distintos 2 a 3 horas y respete cada máximo diario."
    ),
    ("mycoplasma-sequelae-breathlessness-phlegm-cough", "ko", 6): (
        "입술이 파래지거나 함몰 호흡, 7세 기준 분당 40회 이상이면 즉시 진료받으세요."
    ),
    ("mycoplasma-sequelae-breathlessness-phlegm-cough", "es", 6): (
        "Atención inmediata si hay silbidos, sonidos metálicos o gorgoteos, no puede respirar "
        "acostado, responde lento, o a los 7 años supera 40 respiraciones por minuto."
    ),
    ("toddler-mycoplasma-resistant-recovery-no-antibiotics", "es", 9): (
        "Busque atención inmediata por dificultad respiratoria, labios azules, letargo, "
        "no poder beber o 8 horas sin orinar."
    ),
    ("toddler-mycoplasma-resistant-recovery-no-antibiotics", "en", 9): (
        "Seek immediate care for breathing trouble, blue lips, severe lethargy, inability to drink, "
        "or no urine for 8 hours."
    ),
    ("mycoplasma-post-treatment-fever-fatigue-relapse", "es", 9): (
        "Atención inmediata por fiebre sobre 39°C; en menores de 3 meses, desde 38°C. "
        "También por dificultad respiratoria, conciencia alterada u 8 horas sin orinar."
    ),
    ("mycoplasma-post-treatment-fever-fatigue-relapse", "es", 4): (
        "Durante la recuperación, virus comunes pueden causar síntomas intensos."
    ),
    ("mycoplasma-doxycycline-low-fever-care", "es", 8): (
        "Doxiciclina: con comida y agua, según indicación médica."
    ),
    ("mycoplasma-doxycycline-low-fever-care", "ko", 9): (
        "38.5도 이상 고열, 숨참, 깨우기 어려움, 물·음식 거부나 8시간 무뇨면 즉시 병원에 가세요."
    ),
}

SCENE_CLAIMS = {
    ("child-yellow-postnasal-drip-sinusitis-reassessment", "es", 9): (
        "Seek medical care for fever above 38.5°C lasting more than 3 days, facial pain, headache, or breathing difficulty."
    ),
    ("two-month-vaccine-fever-emergency", "ko", 7): (
        "Seek medical care if fever lasts over 48 hours or feeding falls by half; no urination for 8 hours requires emergency evaluation."
    ),
    ("two-month-vaccine-fever-emergency", "en", 7): (
        "Seek medical care if fever lasts over 48 hours or feeding falls by half; no urination for 8 hours requires emergency evaluation."
    ),
    ("two-month-vaccine-fever-emergency", "es", 7): (
        "Seek medical care if fever lasts over 48 hours or feeding falls by half; no urination for 8 hours requires emergency evaluation."
    ),
    ("two-month-vaccine-fever-emergency", "ko", 8): (
        "For this 5.4kg infant and acetaminophen concentration 160mg/5mL, the source recommends 1.7 to 2.5mL per dose every 4 to 6 hours, no more than 5 times daily."
    ),
    ("two-month-vaccine-fever-emergency", "en", 8): (
        "For this 5.4kg infant and acetaminophen concentration 160mg/5mL, the source recommends 1.7 to 2.5mL per dose every 4 to 6 hours, no more than 5 times daily."
    ),
    ("two-month-vaccine-fever-emergency", "es", 8): (
        "For this 5.4kg infant and acetaminophen concentration 160mg/5mL, the source recommends 1.7 to 2.5mL per dose every 4 to 6 hours, no more than 5 times daily."
    ),
    ("infant-pneumonia-contagious-sibling-incubation", "ko", 7): (
        "Fever at 38°C or higher with cough, breathing difficulty, or lethargy is concerning; in infants under 3 months, 38°C or higher requires immediate medical evaluation."
    ),
    ("infant-pneumonia-contagious-sibling-incubation", "en", 7): (
        "Fever at 38°C or higher with cough, breathing difficulty, or lethargy is concerning; in infants under 3 months, 38°C or higher requires immediate medical evaluation."
    ),
    ("infant-pneumonia-contagious-sibling-incubation", "es", 7): (
        "Fever at 38°C or higher with cough, breathing difficulty, or lethargy is concerning; in infants under 3 months, 38°C or higher requires immediate medical evaluation."
    ),
    ("child-yellow-postnasal-drip-sinusitis-reassessment", "ko", 7): (
        "Contact a pediatrician if yellow nasal discharge persists for 3 to 4 days despite home care."
    ),
    ("child-yellow-postnasal-drip-sinusitis-reassessment", "en", 7): (
        "Contact a pediatrician if yellow nasal discharge persists for 3 to 4 days despite home care."
    ),
    ("child-yellow-postnasal-drip-sinusitis-reassessment", "es", 7): (
        "Contact a pediatrician if yellow nasal discharge persists for 3 to 4 days despite home care."
    ),
    ("40c-fever-antipyretic-tepid-compress", "ko", 2): (
        "A fever may reach 40°C, but infants under 3 months need immediate care at 38°C or higher and infants 3 to 6 months at 39°C or higher."
    ),
    ("40c-fever-antipyretic-tepid-compress", "en", 2): (
        "A fever may reach 40°C, but infants under 3 months need immediate care at 38°C or higher and infants 3 to 6 months at 39°C or higher."
    ),
    ("40c-fever-antipyretic-tepid-compress", "es", 2): (
        "A fever may reach 40°C, but infants under 3 months need immediate care at 38°C or higher and infants 3 to 6 months at 39°C or higher."
    ),
    ("40c-fever-antipyretic-tepid-compress", "ko", 4): (
        "Alternate antipyretics only if one medicine is completely ineffective, keep 2 to 3 hours between different medicines, and obey each medicine's daily maximum."
    ),
    ("40c-fever-antipyretic-tepid-compress", "en", 4): (
        "Alternate antipyretics only if one medicine is completely ineffective, keep 2 to 3 hours between different medicines, and obey each medicine's daily maximum."
    ),
    ("40c-fever-antipyretic-tepid-compress", "es", 4): (
        "Alternate antipyretics only if one medicine is completely ineffective, keep 2 to 3 hours between different medicines, and obey each medicine's daily maximum."
    ),
    ("mycoplasma-sequelae-breathlessness-phlegm-cough", "ko", 6): (
        "Seek immediate care for blue lips, chest retractions, or at age 7 a breathing rate of 40 or more per minute."
    ),
    ("toddler-mycoplasma-resistant-recovery-no-antibiotics", "es", 9): (
        "Seek immediate care for breathing difficulty, blue lips, severe lethargy, inability to drink, "
        "or no urination for 8 hours."
    ),
    ("toddler-mycoplasma-resistant-recovery-no-antibiotics", "en", 9): (
        "Seek immediate care for breathing difficulty, blue lips, severe lethargy, inability to drink, "
        "or no urination for 8 hours."
    ),
    ("mycoplasma-post-treatment-fever-fatigue-relapse", "es", 9): (
        "Seek immediate care for fever above 39°C; for infants under 3 months, 38°C or higher; "
        "also for breathing difficulty, altered consciousness, or no urination for 8 hours."
    ),
    ("mycoplasma-doxycycline-low-fever-care", "es", 8): (
        "Take prescribed doxycycline with food and plenty of water, following the clinician's directions."
    ),
}

SCENE_OVERLAYS = {
    ("mycoplasma-sequelae-breathlessness-phlegm-cough", "ko", 6): [
        {
            "type": "label",
            "from": [0.5, 0.68],
            "to": [0.5, 0.68],
            "label_position": [0.5, 0.68],
            "color": "#E5482F",
            "text": "7세 기준 분당 40회 이상",
        }
    ]
}


def main() -> None:
    for (key, language), narrations in OVERRIDES.items():
        path = CONFIGS / f"{key}.production.{language}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if len(narrations) != len(data["scenes"]):
            raise ValueError(f"Override length mismatch for {key} [{language}]")
        for scene, narration in zip(data["scenes"], narrations):
            scene["narration"] = narration
            scene["subtitle"] = narration
            scene["caption_chunks"] = [narration]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"COMPACTED {path.relative_to(ROOT)}")
    for (key, language, index), narration in SCENE_OVERRIDES.items():
        path = CONFIGS / f"{key}.production.{language}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        scene = data["scenes"][index - 1]
        scene["narration"] = narration
        scene["subtitle"] = narration
        scene["caption_chunks"] = [narration]
        if (key, language, index) in SCENE_CLAIMS:
            scene["medical_claim"] = SCENE_CLAIMS[(key, language, index)]
        if (key, language, index) in SCENE_OVERLAYS:
            scene["overlays"] = SCENE_OVERLAYS[(key, language, index)]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"COMPACTED {path.relative_to(ROOT)} scene {index}")


if __name__ == "__main__":
    main()
