# 전체 최종 영상 TTS·자막 재검사

- 모델: `gemini-2.5-flash`
- 완료 영상: 39 / 요청 실패: 0
- 장면별 검사 로그: 390
- 판정: {'PASS': 35, 'WARN': 3, 'FAIL': 1}
- 이슈 범주: {'SOURCE_CONTRADICTION': 4, 'CLINICAL_DISTINCTION_MISSING': 1, 'OTHER_VISUAL_ERROR': 1, 'TRIAGE_OMISSION': 1}
- 실제 TTS·자막·오디오 이슈: 0건
- 의료·시각·진료기준 이슈: 7건
- 로컬 SRT/대본 불일치: 0개 영상
- 잘못된 1~10 장면 로그: 0개 영상

## 장면별 회귀 체크 집계

- 실패 장면 수: {'numbers_and_units_match': 1}
- 영향받은 영상 수: {'numbers_and_units_match': 1}
- 피드백 기준별 FAIL 영상 수: {'caption_clause_coverage': 1, 'triage_adequacy': 2, 'drug_specific_redosing': 1}

## 로컬 SRT·대본 불일치 후보

- 없음

## TTS·자막·오디오 수정 후보

| 영상 | 장면 | 시각 | 심각도 | 범주 | 문제 |
|---|---:|---|---|---|---|
| - | - | - | - | - | 감지된 이슈 없음 |

## 의료·시각·진료기준 수정 후보

| 영상 | 장면 | 심각도 | 범주 | 문제 |
|---|---:|---|---|---|
| baby-enteritis-medicine-stop.en | 9 | medium | CLINICAL_DISTINCTION_MISSING | 원문에서는 '하루 3회 이상 묽은 설사를 반복하는 경우'를 지체 없이 소아과 의사에게 진료를 받아야 하는 긴급 상황으로 명시하고 있습니다. 영상의 'Three loose stools alone are not an emergency'라는 문구는 '묽은 설사'와 '무른 변'의 구분을 모호하게 하여, 부모가 심각한 설사 증상을 경미하게 오인하고 진료를 지연할 위험이 있습니다. |
| baby-enteritis-medicine-stop.ko | 6 | low | SOURCE_CONTRADICTION | 증상이 호전되어 정상 변을 보고 복통이 없을 경우, 출처는 약 복용을 계속 중단해도 된다고 명시하지만, 영상은 남은 약의 복용 계획을 의료진과 확인하라고 권고합니다. |
| baby-enteritis-medicine-stop.ko | 7 | low | SOURCE_CONTRADICTION | 복통이나 설사가 재발할 경우, 출처는 월요일 병원 진료 전까지 남은 약을 다시 복용시키라고 명시하지만, 영상은 임의로 재시작하지 말고 의료진에게 문의하라고 권고합니다. |
| infant-wheezing-pneumonia-antibiotics.ko | 8 | low | OTHER_VISUAL_ERROR | 의인화된 기관지 캐릭터가 아기를 안고 옷을 느슨하게 해주는 모습이 실제 사람의 모습이 아니어서 일부 시청자에게는 다소 추상적으로 느껴질 수 있습니다. |
| pediatric-fever-alternating-meds.en | 1 | high | TRIAGE_OMISSION | 영상에서 중이염 치료를 위한 항생제를 처방받은 기간 동안 끝까지 복용해야 한다는 중요한 지침이 누락되었습니다. 이는 환자가 임의로 항생제 복용을 중단할 위험을 높여 치료 실패나 합병증으로 이어질 수 있습니다. |
| pediatric-tamiflu-dosing-flexibility.es | 8 | high | SOURCE_CONTRADICTION | 영상에서 구토 후 약 복용 재개에 대해 "다시 복용하기 전에 상담하라"고 조언하지만, 원문 출처는 오셀타미비르 복용 후 1시간 이내 구토 시 "즉시 1회 용량을 다시 먹여야 한다"고 명시적으로 지시합니다. 이는 약물별 재복용 지침에 대한 중요한 불일치입니다. |
| pediatric-tamiflu-dosing-flexibility.ko | 8 | low | SOURCE_CONTRADICTION | 구토 시 약 재복용 기준 시간이 소스(1시간 이내)와 다릅니다. |
