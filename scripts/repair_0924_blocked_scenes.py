#!/usr/bin/env python3
"""Repair medically misleading or text-dependent scenes in the 2026-09-24 batch."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "9" / "24" / "configs"


VISUALS = {
    "child-yellow-postnasal-drip-sinusitis-reassessment": {
        "scene": 5,
        "prompt": (
            "A clean semi-stylized 3D pediatric nasal-rinse safety demonstration. A school-age child stands at "
            "a sink, leans the upper body forward, keeps the chin slightly tucked and mouth open, and gently uses "
            "a purpose-made saline rinse bottle while a caregiver supervises. The face remains above the sink; "
            "never recline the child or tilt the head backward. No needle, medicine, swallowing, text, "
            "letters, numbers, labels, logos, watermarks, dialogue, lip-sync, extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Clean semi-stylized 3D pediatric scene of a school-age child leaning forward over a sink with chin "
            "slightly tucked for a supervised saline nasal rinse using a purpose-made rinse bottle. Never reclined "
            "and never head tilted backward. No needle, medicine, text, letters, digits, labels, logos, "
            "or watermarks."
        ),
        "shot_design": {
            "camera_profile": "lateral_reveal",
            "beat_one": "0.0-1.5 seconds: side view clearly establishes the child leaning forward over the sink",
            "beat_two": "1.5-4.5 seconds: supervised gentle saline rinse with chin tucked and mouth open",
            "payoff_frame": "4.5-6.0 seconds: hold on the safe forward-leaning posture above the sink",
            "depth_layers": "sink foreground, child and caregiver midground, softly blurred bathroom background",
            "overlay_safe_zone": "upper right",
            "sound_cues": "gentle running water and quiet room ambience",
            "transition_out": "soft fade",
        },
    },
    "baby-38c-fever-active-antipyretic": {
        "scene": 9,
        "prompt": (
            "A respectful clean semi-stylized 3D pediatric emergency-warning scene. An awake child is unusually "
            "limp and difficult to engage while a concerned caregiver gently checks responsiveness, notices an "
            "unusually dry plain diaper, and promptly reaches for emergency help. Do not show clocks, timers, "
            "screens, floating words, written time, urine, medicine, or medication-administration devices. No "
            "text, letters, numbers, labels, logos, watermarks, dialogue, lip-sync, extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Respectful clean semi-stylized 3D pediatric scene: awake but unusually limp child, caregiver checking "
            "responsiveness beside a plain dry diaper and reaching for emergency help. No clocks, timers, screens, "
            "written time, urine, medicine, text, letters, digits, labels, logos, or watermarks."
        ),
        "shot_design": {
            "camera_profile": "pov_travel",
            "beat_one": "0.0-1.5 seconds: caregiver checks an awake but unusually limp child",
            "beat_two": "1.5-4.5 seconds: caregiver notices the plain dry diaper and promptly reaches for help",
            "payoff_frame": "4.5-6.0 seconds: hold on the caregiver taking urgent action",
            "depth_layers": "caregiver hand foreground, child midground, softly blurred room background",
            "overlay_safe_zone": "upper right",
            "sound_cues": "quiet urgent room ambience",
            "transition_out": "quick fade",
        },
    },
    "40c-fever-antipyretic-tepid-compress": {
        "scene": 9,
        "prompt": (
            "A respectful clean semi-stylized 3D pediatric emergency-action scene. A worried caregiver "
            "supports an awake but unusually drowsy child in an upright position, observes the child's breathing, "
            "and promptly reaches for a phone to seek emergency help. Focus on the caregiver recognizing danger "
            "and acting quickly; do not visibly depict blue skin, unconsciousness, graphic respiratory distress, "
            "panic, medicine, or medication-administration devices. No text, letters, numbers, labels, logos, "
            "watermarks, dialogue, lip-sync, extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Respectful clean semi-stylized 3D pediatric emergency-action scene: a worried caregiver supports "
            "an awake but unusually drowsy child upright while checking breathing and reaching for a phone. "
            "No blue skin, unconsciousness, graphic distress, medicine, text, letters, digits, labels, logos, "
            "or watermarks."
        ),
        "shot_design": {
            "camera_profile": "lateral_reveal",
            "beat_one": "0.0-1.5 seconds: caregiver supports an awake, unusually drowsy child upright",
            "beat_two": "1.5-4.5 seconds: caregiver observes breathing and promptly reaches for emergency help",
            "payoff_frame": "4.5-6.0 seconds: hold on the caregiver taking urgent action",
            "depth_layers": "child and caregiver midground, phone foreground, softly blurred room background",
            "overlay_safe_zone": "upper left",
            "sound_cues": "quiet urgent room ambience",
            "transition_out": "quick fade",
        },
        "copy": {
            "ko": "입술이 파래지거나 갈비뼈 아래가 들어가거나, 숨쉬기 힘들고 깨우기 어렵다면 즉시 응급실로 가세요.",
            "en": "Go to the ER now for blue lips, chest indrawing, breathing trouble, or difficulty waking.",
            "es": "Vaya a emergencias por labios azules, hundimiento del pecho, dificultad para respirar o despertar.",
        },
        "claim": "Blue lips, chest indrawing, breathing difficulty, or difficulty waking require immediate emergency care.",
    },
    "40c-fever-antipyretic-tepid-compress-dehydration": {
        "config_key": "40c-fever-antipyretic-tepid-compress",
        "scene": 8,
        "prompt": (
            "A respectful clean semi-stylized 3D pediatric hydration and emergency-action scene. A caregiver "
            "keeps an awake febrile child in light clothing and offers frequent small sips from an ordinary open "
            "cup. The caregiver then notices a very dry mouth and absence of tears and promptly reaches for help. "
            "Do not show medicine, diapers, urine, graphic distress, or medication-administration devices. No "
            "text, letters, numbers, labels, logos, watermarks, dialogue, lip-sync, extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Respectful clean semi-stylized 3D pediatric scene: lightly dressed awake child upright with caregiver "
            "offering small sips from an ordinary open cup, caregiver concerned about a dry mouth and absent tears. "
            "No medicine, diapers, urine, text, letters, digits, labels, logos, or watermarks."
        ),
        "shot_design": {
            "camera_profile": "hero_pullback",
            "beat_one": "0.0-1.5 seconds: caregiver offers small sips from an open cup to an upright child",
            "beat_two": "1.5-4.5 seconds: caregiver recognizes dehydration warning signs and reaches for urgent help",
            "payoff_frame": "4.5-6.0 seconds: hold on prompt caregiver action",
            "depth_layers": "open cup foreground, child and caregiver midground, softly blurred room background",
            "overlay_safe_zone": "upper right",
            "sound_cues": "quiet room ambience",
            "transition_out": "quick fade",
        },
        "copy": {
            "ko": "옷을 가볍게 하고 물을 자주 주세요. 8시간 넘게 소변이 없거나 눈물과 침이 거의 없으면 응급실로 가세요.",
            "en": "Dress lightly and offer fluids often. Seek emergency care for no urine over 8 hours or almost no tears or saliva.",
            "es": "Use ropa ligera y ofrezca líquidos. Vaya a emergencias si pasan 8 horas sin orinar o casi no hay lágrimas ni saliva.",
        },
        "claim": "Offer fluids and seek emergency care for severe dehydration signs such as no urination for over 8 hours or almost no tears or saliva.",
    },
    "40c-fever-antipyretic-tepid-compress-neurologic": {
        "config_key": "40c-fever-antipyretic-tepid-compress",
        "scene": 10,
        "prompt": (
            "A respectful clean semi-stylized 3D pediatric emergency-action scene. An unwell but awake child "
            "rests upright with poor eye contact while a caregiver notices concerning neck discomfort and promptly "
            "calls for emergency help. Focus on recognition and action, without depicting vomiting, unconsciousness, "
            "graphic distress, medicine, or medication-administration devices. No text, letters, numbers, labels, "
            "logos, watermarks, dialogue, lip-sync, extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Respectful clean semi-stylized 3D pediatric emergency-action scene: awake unwell child upright with "
            "poor eye contact and neck discomfort, caregiver promptly reaching for help. No vomiting, medicine, "
            "text, letters, digits, labels, logos, or watermarks."
        ),
        "shot_design": {
            "camera_profile": "parallax_arc",
            "beat_one": "0.0-1.5 seconds: caregiver notices poor eye contact and concerning neck discomfort",
            "beat_two": "1.5-4.5 seconds: caregiver supports the awake child and promptly calls for emergency help",
            "payoff_frame": "4.5-6.0 seconds: stable frame emphasizes urgent caregiver action",
            "depth_layers": "caregiver foreground, child midground, softly blurred room background",
            "overlay_safe_zone": "upper left",
            "sound_cues": "quiet urgent room ambience",
            "transition_out": "fade to closing frame",
        },
        "copy": {
            "ko": "목이 뻣뻣하거나 심한 두통과 반복 구토, 계속 누워 있거나 눈맞춤이 줄면 즉시 응급실 진료를 받으세요.",
            "en": "Seek emergency medical care for a stiff neck, severe headache with repeated vomiting, persistent lying down, or poor eye contact.",
            "es": "Busque atención médica urgente por rigidez de cuello, dolor de cabeza con vómitos repetidos, postración o poco contacto visual.",
        },
        "claim": "Stiff neck, severe headache with repeated vomiting, persistent lying down, or poor eye contact require immediate emergency evaluation.",
    },
    "mycoplasma-post-treatment-fever-fatigue-relapse": {
        "scene": 4,
        "prompt": (
            "A clean semi-stylized 3D pediatric medical visualization of a school-age child's upper body, "
            "with clearly child-appropriate proportions and clothing. A gentle translucent cutaway highlights "
            "the child's airways while a few neutral abstract particles approach and the child appears mildly "
            "fatigued. Do not depict an adult torso, diagnose a specific new infection, or show medicine or "
            "medication-administration devices. No text, letters, numbers, labels, logos, watermarks, dialogue, "
            "lip-sync, extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Clean semi-stylized 3D pediatric medical illustration of a clothed school-age child's upper body "
            "with unmistakably child-appropriate proportions, mild fatigue, and a subtle translucent airway "
            "highlight. No adult torso, medicine, text, letters, digits, labels, logos, or watermarks."
        ),
        "shot_design": {
            "camera_profile": "xray_push",
            "beat_one": "0.0-1.5 seconds: camera approaches a clothed school-age child with mild fatigue",
            "beat_two": "1.5-4.5 seconds: a gentle pediatric airway cutaway appears as neutral particles approach",
            "payoff_frame": "4.5-6.0 seconds: hold on the child-appropriate respiratory visualization",
            "depth_layers": "child foreground, subtle airway cutaway midground, softly blurred room background",
            "overlay_safe_zone": "upper left",
            "sound_cues": "soft room ambience",
            "transition_out": "gentle pullback",
        },
    },
    "infant-pneumonia-contagious-sibling-incubation": {
        "scene": 3,
        "include_character": False,
        "prompt": (
            "A clean semi-stylized 3D pediatric timeline metaphor without any pathogen character. A healthy "
            "young child continues normal quiet home activities as the room lighting gently shifts through "
            "several day-to-evening changes, then later develops a mild cough and is comforted by a caregiver. "
            "Do not depict bacteria, viruses, pneumococcus, calendars, clocks, timers, medicine, or medication-"
            "administration devices. No text, letters, numbers, labels, logos, watermarks, dialogue, lip-sync, "
            "extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Clean semi-stylized 3D pediatric scene of a healthy young child doing a quiet home activity with "
            "a caregiver nearby, suitable for a later transition to mild cough after an incubation period. No "
            "pathogen character, bacteria, viruses, calendars, clocks, medicine, text, letters, digits, labels, "
            "logos, or watermarks."
        ),
        "shot_design": {
            "camera_profile": "macro_dive",
            "beat_one": "0.0-1.5 seconds: healthy child continues an ordinary quiet home activity",
            "beat_two": "1.5-4.5 seconds: gentle changes in natural room lighting imply time passing without clocks or calendars",
            "payoff_frame": "4.5-6.0 seconds: the child later coughs mildly and a caregiver offers comfort",
            "depth_layers": "caregiver foreground, child midground, softly blurred home background",
            "overlay_safe_zone": "upper left",
            "sound_cues": "quiet home ambience and one mild cough",
            "transition_out": "soft dissolve",
        },
    },
    "infant-pneumonia-contagious-sibling-incubation-prevention": {
        "config_key": "infant-pneumonia-contagious-sibling-incubation",
        "scene": 8,
        "include_character": True,
        "prompt": (
            "A single continuous clean semi-stylized 3D pediatric home scene. A child washes hands at a sink "
            "while a caregiver supervises. In the same visible room, an open window provides ventilation, a "
            "simple balanced meal rests on a table, and a neatly made bed suggests adequate sleep. A small "
            "established germ mascot may remain quietly in the far background but must not be labeled or shown "
            "as the only cause of pneumonia. The camera gently pulls back once to reveal all prevention cues; "
            "do not jump between locations. No medicine or medication-administration devices. No text, letters, "
            "numbers, labels, logos, watermarks, dialogue, lip-sync, extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Single clean semi-stylized 3D pediatric home scene: child washing hands with caregiver supervision, "
            "open window, balanced meal on a table, and neatly made bed all visible in one coherent room. A small "
            "unlabeled established germ mascot is far in the background. No medicine, text, letters, digits, "
            "labels, logos, or watermarks."
        ),
        "shot_design": {
            "camera_profile": "macro_dive",
            "beat_one": "0.0-1.5 seconds: close view of supervised handwashing",
            "beat_two": "1.5-4.5 seconds: one gentle pullback reveals the open window, balanced meal, and made bed in the same room",
            "payoff_frame": "4.5-6.0 seconds: stable wide frame holds all prevention cues together",
            "depth_layers": "hands foreground, child and caregiver midground, window table and bed background",
            "overlay_safe_zone": "upper right",
            "sound_cues": "running water and gentle room ambience",
            "transition_out": "soft fade",
        },
        "copy": {
            "ko": "손 씻기와 환기, 충분한 수면과 영양은 감염 위험을 줄이는 데 도움이 됩니다.",
            "en": "Handwashing, ventilation, enough sleep, and good nutrition can help reduce infection risk.",
            "es": "Lavarse las manos, ventilar, dormir bien y comer adecuadamente ayuda a reducir el riesgo de infección.",
        },
        "claim": "Handwashing, ventilation, adequate sleep, and good nutrition can help reduce infection risk but do not guarantee prevention.",
    },
    "toddler-mycoplasma-resistant-recovery-no-antibiotics": {
        "scene": 7,
        "prompt": (
            "A clean semi-stylized 3D pediatric recovery scene. A caregiver calmly observes a toddler "
            "who begins tired and resting, then gradually sits up, drinks from an ordinary open cup, and "
            "returns to quiet play. Emphasize improving alertness and comfort without showing medicine, "
            "clocks, timers, calendars, or medication-administration devices. No text, letters, numbers, "
            "labels, logos, watermarks, dialogue, lip-sync, extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Clean semi-stylized 3D pediatric scene of a concerned caregiver beside a tired toddler who is "
            "sitting up and becoming more alert, with an ordinary open drinking cup nearby. No medicine, "
            "clocks, timers, calendars, medication-administration devices, text, letters, digits, labels, "
            "logos, or watermarks."
        ),
        "shot_design": {
            "camera_profile": "pov_travel",
            "beat_one": "0.0-1.5 seconds: caregiver watches a tired toddler resting upright",
            "beat_two": "1.5-4.5 seconds: toddler becomes more alert, takes a sip from an open cup, and reaches for a toy",
            "payoff_frame": "4.5-6.0 seconds: caregiver notes the child's improved comfort and activity",
            "depth_layers": "caregiver foreground, toddler midground, softly blurred home background",
            "overlay_safe_zone": "upper right",
            "sound_cues": "quiet room ambience",
            "transition_out": "gentle fade",
        },
        "copy": {
            "ko": "해열제가 필요한 간격이 길어지고 아이 상태가 좋아지면 회복 신호일 수 있습니다.",
            "en": "Needing fever medicine less often along with improved activity may be a sign of recovery.",
            "es": "Necesitar antitérmico con menos frecuencia y ver más actividad puede indicar recuperación.",
        },
        "claim": "Less frequent need for fever medicine together with improving overall condition may indicate recovery.",
    },
    "tonsillitis-without-fever-symptoms": {
        "scene": 7,
        "prompt": (
            "A clean semi-stylized 3D pediatric reassessment scene. A caregiver notices that a school-age "
            "child's throat discomfort is not improving, offers an ordinary open cup of water, and calmly "
            "prepares to leave for a clinic. End at a pediatric clinic entrance with blank unmarked surfaces. "
            "Do not show calendars, clocks, timers, medicine, or medication-administration devices. No text, letters, "
            "numbers, labels, logos, watermarks, dialogue, lip-sync, extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Clean semi-stylized 3D pediatric scene: a caregiver beside a school-age child with persistent "
            "throat discomfort, preparing for a clinic reassessment. Ordinary open water cup only. No calendars, "
            "clocks, medicine, medication-administration devices, text, letters, digits, labels, logos, or watermarks."
        ),
        "shot_design": {
            "camera_profile": "pov_travel",
            "beat_one": "0.0-1.5 seconds: caregiver observes persistent throat discomfort",
            "beat_two": "1.5-4.5 seconds: caregiver helps the child prepare for a clinic reassessment",
            "payoff_frame": "4.5-6.0 seconds: calm arrival at a pediatric clinic entrance",
            "depth_layers": "child and caregiver midground, softly blurred home then clinic background",
            "overlay_safe_zone": "upper left",
            "sound_cues": "quiet room ambience",
            "transition_out": "soft crossfade",
        },
        "copy": {
            "ko": "증상이 3일 이상 지속되거나 점차 악화되면 병원에서 다시 진료받으세요.",
            "en": "If symptoms last more than three days or keep worsening, arrange a medical reassessment.",
            "es": "Si los síntomas duran más de tres días o empeoran, solicite una nueva valoración médica.",
        },
        "claim": "Persistent or worsening symptoms warrant medical reassessment; urgency depends on red flags and severity.",
    },
    "two-month-vaccine-fever-emergency": {
        "scene": 9,
        "prompt": (
            "A respectful clean semi-stylized 3D pediatric emergency-warning scene. An infant is clearly awake "
            "but unusually limp and poorly responsive, eyes partly open and not smiling, while a worried caregiver "
            "gently touches the infant's shoulder and immediately reaches for help. The starting frame must not look "
            "like normal peaceful sleep. Do not depict a seizure or graphic distress. No medicine, injections, oral "
            "medication-administration devices, text, letters, numbers, labels, logos, watermarks, dialogue, lip-sync, extra limbs, or deformation."
        ),
        "asset_prompt": (
            "Respectful clean semi-stylized 3D pediatric emergency-warning scene: an infant is awake but unusually "
            "limp and poorly responsive, eyes partly open, with a worried caregiver gently checking responsiveness. "
            "Clearly not normal sleep; no seizure or graphic distress. No medicine or medication-administration devices, "
            "text, letters, digits, labels, logos, or watermarks."
        ),
        "shot_design": {
            "camera_profile": "hero_pullback",
            "beat_one": "0.0-1.5 seconds: awake infant appears unusually limp and poorly responsive, clearly not asleep",
            "beat_two": "1.5-4.5 seconds: caregiver gently checks responsiveness and reaches for urgent help",
            "payoff_frame": "4.5-6.0 seconds: hold on caregiver taking prompt action",
            "depth_layers": "caregiver hand foreground, awake infant midground, softly blurred room background",
            "overlay_safe_zone": "upper right",
            "sound_cues": "quiet urgent room ambience",
            "transition_out": "quick fade",
        },
    },
}


def main() -> None:
    changed = 0
    for topic, repair in VISUALS.items():
        config_key = repair.get("config_key", topic)
        for language in ("ko", "en", "es"):
            path = CONFIG_DIR / f"{config_key}.production.{language}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            scene = data["scenes"][repair["scene"] - 1]
            scene["prompt"] = repair["prompt"]
            scene["asset_prompt"] = repair["asset_prompt"]
            scene["shot_design"] = repair["shot_design"]
            scene["image"] = None
            scene["overlays"] = []
            if "include_character" in repair:
                scene["include_character"] = bool(repair["include_character"])
            if "copy" in repair:
                copy = repair["copy"][language]
                scene["narration"] = copy
                scene["subtitle"] = copy
                scene["caption_chunks"] = [copy]
                scene["medical_claim"] = repair["claim"]
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += 1
            print(f"UPDATED {path.relative_to(ROOT)} scene {repair['scene']}")
    print(f"Updated {changed} configs")


if __name__ == "__main__":
    main()
