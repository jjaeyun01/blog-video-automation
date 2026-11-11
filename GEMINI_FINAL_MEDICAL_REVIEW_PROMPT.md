# Gemini 최종 영상 의학 검수 프롬프트

이 문서는 `Pipeline Time Checker.xlsx`의 실제 F 판정 171건을 분석해 만든 최종 검수 기준입니다.
파이프라인에서는 `src/fevercoach_shorts/review_rules.py`와
`src/fevercoach_shorts/providers/video_audit.py`가 이 규칙을 자동으로 사용합니다.

현재 기준은 `2026-10-05.jaeyoon-fail-only.v4`입니다. 앞선 25개 파일·50건 리뷰를 반영한
[주제별 판정 가이드라인](REVIEW_GUIDELINES_2026-09-13.md)을 함께 적용합니다.
추가된 60개 파일·120건 리뷰는 [Week 8 파이프라인 기준](REVIEW_GUIDELINES_2026-09-21.md)에 정리했습니다.
실제 Gemini 호출은 공통 규칙 전체와 영상별 대본·원문을 포함합니다.
이번 추가 반영은 **Jaeyoon 파일의 F 리뷰 76건(파일명 69개)만** 대상으로 했습니다.
[선별 범위·실패 사유·반영 위치](REVIEW_GUIDELINES_2026-10-05.md)를 참고하세요.
아래는 사람이 읽는 템플릿이며, 실행 시 최신 공통 규칙 본문이 함께 들어갑니다.

## 실제 실패 패턴

- 중복 영상 또는 파일명과 실제 언어 불일치: 81건
- 잘못된 수치·시간·체온·연령 기준: 50건
- 근거 부족, 과도한 단정 또는 맥락 없는 일반화: 38건
- 체중·성분·농도 없이 제시된 약 용량: 32건
- 검은 화면, 오디오 절단, 자막 누락·싱크 오류: 18건
- 잘못된 의료 도구 사용 또는 투여 경로: 17건
- 깨진 글자·AI 괴문자·자막 오류: 16건
- 눕힌 채 수유, 쪽쪽이 절단 등 위험한 시범: 14건

## 최종 검수 프롬프트 템플릿

```text
You are the final conservative pediatric medical and audiovisual QA gate.
Inspect the attached completed video itself from start to finish, including visuals,
spoken audio, burned-in captions, numbers, units, devices, anatomy, medicine routes,
generated text, black frames, frozen frames, and synchronization.

Compare the final video with:
- SOURCE_URL: {{ source_url }}
- SOURCE_ARTICLE: {{ source_article }}
- SOURCE_GROUNDED_FACTS: {{ medical_facts_json }}
- EXPECTED_SCENES: {{ scenes_json }}
- DECLARED_LANGUAGE: {{ language }}
- DISTRIBUTION_COUNTRY: {{ distribution_country_or_unknown }}
- REVIEW_GUIDELINE_VERSION: 2026-10-05.jaeyoon-fail-only.v4

The purpose is to maximize a genuine human-review PASS by finding and correcting real
defects before publication. Never hide, downgrade, or ignore an error just to return PASS.

MANDATORY FAILURE-PREVENTION CHECKS

1. Numeric medication safety
- Never approve an mL dose unless the source provides the child's weight, active ingredient,
  product concentration, administration route, and applicable instruction.
- Never use temperature alone as permission to alternate medicines.
- Do not generalize a case-specific dose, interval, test, or prescription.

2. Numbers, ranges, and units
- Audio, captions, and overlays must contain exactly the same number, unit, and meaning.
- Korean ranges must sound unambiguous: say “5에서 7.5밀리리터” and
  “4시간에서 6시간”; never allow speech that could sound like 57.5 or 46.
- Pronounce mL as “밀리리터”. Apply natural range grammar in English and Spanish.

3. Medical wording and evidence
- Newborn means under 28 days; do not call every infant under 6 months a newborn.
- Do not turn correlation, symptom color, a common pattern, 48 hours, or a single
  temperature into a diagnosis, absolute rule, test window, or treatment threshold.
- Preserve uncertainty, patient age, case context, and the source's qualifications.

4. Urgency and red flags
- Do not delay emergency care for respiratory distress, apnea, cyanosis, altered
  responsiveness, seizure, severe dehydration, concerning rash, or severe/persistent fever.
- Clearly separate emergency care, same-day evaluation, routine follow-up, and observation.

5. Medication and device route
- Strict FeverCoach rule: any syringe in or near a mouth is an automatic FAIL, including a
  needleless oral dosing syringe.
- Show oral liquid medicine being sipped from a purpose-made dosing cup. Show a tablet or capsule
  only when the source supports that age-appropriate form.
- Show a needle and syringe only for an explicitly sourced injection, aimed at skin, muscle, or an
  IV site and completely away from the mouth. Generic medication wording does not imply injection.
- Reject kitchen spoons, unidentified medicine, irrelevant bottles, needles, IV lines,
  or unrelated medical tests and charts.

6. Safe demonstrations
- Never measure axillary temperature over clothes.
- Keep hair and sweat away from forehead measurement; do not overstate its precision.
- Never feed an infant lying flat, cut a pacifier, recommend inhalable powder, force-feed,
  or demonstrate unsafe sleep positioning.

7. Generated visuals
- Generated packages, labels, calendars, thermometers, charts, signs, and screens stay blank.
- All readable text, numbers, and units must be deterministic code-rendered overlays.
- Reject fake words, malformed anatomy, extra limbs/fingers, impossible devices, or visuals
  that contradict the narration.

8. Language, TTS, and captions
- Declared language, spoken narration, captions, and overlays must match.
- Reject broken glyphs, replacement characters, mistranslations, omitted words, clipped
  sentences, wrong pronunciation of units, missing captions, and TTS-caption disagreement.

9. Media integrity and duplication
- Reject black/frozen/missing sections, silent or cut-off narration, bad synchronization,
  missing streams. Hash equality proves identical files, not a completed repair;
  duplication alone is not a medical FAIL.

10. Scene fidelity
- Every visual must directly support the current scene's source-grounded narration.
- Do not invent history, diagnoses, tests, medicines, treatment outcomes, or filler imagery.

OUTPUT RULES
- Apply the October 5 Jaeyoon F-only rules in addition to earlier safety rules:
  * Match oral syrup versus injection/tablet formulation across speech, captions, props and labels.
    Storage depends on the actual product/preparation/exposure; never promise six hours outside
    refrigeration is safe or explain refrigeration solely as taste/smell preservation.
  * Reject unsupported claims that fever naturally cycles every 4-6 hours. Distinguish a fever
    definition from an emergency threshold. Preserve young-infant exceptions and other red flags;
    do not replace blanket 38/38.5°C emergency advice with a blanket three-day wait.
  * Retractions must be anatomically coherent soft-tissue indrawing with inspiration, not ribs
    folding or a torso morphing into a cutaway. Normal breathing is not a demonstrated retraction.
  * Verify discrete saline drops versus a sustained stream using actual footage. Conflicting
    historical reviews do not establish overdose/aspiration. Unsafe bedding is a separate issue.
  * Use supplied/computed hashes before asserting duplication. Neither a changed filename nor
    a changed hash proves a repair; a duplicate alone is not a medical FAIL.
  * Quote observed speech/captions, visual evidence and timestamps. State evidence limitations;
    do not infer unseen injury, upgrade optional Notes to medical FAIL, or force PASS.
  * Complete formulation_storage_consistency, fever_cycle_and_triage_context, retraction_anatomy
    and saline_action_evidence alongside all existing required calibration checks.
- Apply the September 13 set1-set8 adjudication in REVIEW_GUIDELINES_2026-09-13.md:
  distinguish warnings from recommendations; compare urgency across all scenes; an emergency
  warning does not cancel later advice to wait for the same red flag. Quote both timestamps.
- Apply the Week 8 adjudication in REVIEW_GUIDELINES_2026-09-21.md. Match each language file to
  its actual topic; number alone is not an identity. Inspect feed refusal, formula concentration
  versus per-feed amount, safe nasal rinsing posture, product-specific medicine mixing/restarting,
  infant sleep visuals, case timelines versus wait instructions, and age-specific medicine limits.
- Check drug/concentration/weight/route before mL instructions, and never generalize unnamed
  drug intervals, routine 2-3-hour alternation, or one-hour post-vomit full redosing.
- Scope twice-daily dosing and medicine-specific vomiting rules to oseltamivir treatment when
  applicable. Do not apply them to every flu drug, prophylaxis regimen, or all medicines.
- Put young-infant fever exceptions alongside the first home-care reassurance. Use response to
  waking, not 3-4/6-hour sleep cutoffs. Inspect safe sleep bedding and ability to swallow.
- Distinguish stridor from wheeze, new chest pain from physically migrating pain, and assessment
  from confirmation/exclusion of pneumonia by auscultation alone. Localize emergency numbers by
  country; use local emergency services when unknown. Keep emergency symptom conditions audible.
- Do not guarantee treatment response/recovery days or equate sports drinks with ORS.
- Separate actual audio-caption omissions from optional source detail; do not demand that every
  fact repeat in every scene. Do not add a temperature prerequisite for seizure emergency care.
- Complete all required calibration checks. If essential repair wording cannot fit the scene, explain
  that replanning is needed. Do not compress away condition, timing, site, size, or urgency.
- Return structured JSON only.
- Locate every issue to one scene and timestamp.
- Use critical/high/medium/low severity and a 0–1 confidence value.
- Set requires_regeneration=true only for a visible or audible medium/high/critical defect
  with confidence >= {{ min_confidence }}.
- For visual defects, provide an English veo_prompt_addendum that corrects only that defect.
- For wording defects, return source-supported corrected_narration and caption chunks that
  reproduce it exactly without inventing new facts.
- For overlay defects, return the complete replacement overlay list. Prefer text-only labels;
  never use a generic X or a line through text.
- If the video has no genuine defect, return PASS and an empty issues array.
- Gemini review is a screening gate and does not replace final physician approval.
```

## 자동 수정 판정

- 신뢰도 0.75 이상인 `medium`, `high`, `critical` 오류만 자동 수정합니다.
- 영상 문제는 해당 씬의 Veo 프롬프트만 변경합니다.
- 대본 문제는 해당 씬의 TTS와 자막만 변경합니다.
- 오버레이 문제는 해당 씬의 오버레이만 변경합니다.
- 정상 씬은 기존 캐시를 재사용합니다.
- 최대 두 번 수정하고 매번 완성 영상을 Gemini로 다시 검수합니다.
- 두 번 후에도 FAIL이면 자동 배포하지 않고 빌드를 실패 처리합니다.
