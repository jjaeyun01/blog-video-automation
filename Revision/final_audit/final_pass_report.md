# Revision 영상 의학 재감사·최종 자동 판정

- 총 39편: PASS 39, WARN 0, FAIL 0, UNVERIFIED 0
- 1차 Gemini 원판정: PASS 35, WARN 3, FAIL 1; 이 중 6편은 별도 근거·2차 Gemini 재판정을 반영했습니다.
- PASS는 Gemini 모델 및 로컬 검사의 자동 선별 결과이며 의사의 최종 승인을 대체하지 않습니다.
- WARN·FAIL·UNVERIFIED 영상은 최종 PASS 영상으로 간주하지 않습니다.

| 영상 | 최종 판정 | Gemini | 이슈 | 이유 |
|---|---|---|---:|---|
| baby-40c-fever-no-other-symptoms.en | PASS | PASS | 0 | - |
| baby-40c-fever-no-other-symptoms.es | PASS | PASS | 0 | - |
| baby-40c-fever-no-other-symptoms.ko | PASS | PASS | 0 | - |
| baby-enteritis-medicine-stop.en | PASS | WARN | 1 | 2차 Gemini가 1차의 '무른 변 3회만으로 응급은 아니다' 지적을 원 피드백 기준과 위험징후 문맥에 비추어 무효로 재판정했습니다. 1차 장면 9의 numbers_and_units_match=false도 음성·자막 숫자 불일치가 아니라 출처 해석을 잘못 넣은 것입니다. |
| baby-enteritis-medicine-stop.es | PASS | PASS | 0 | - |
| baby-enteritis-medicine-stop.ko | PASS | WARN | 2 | 2차 Gemini가 처방약 중단·재시작을 임의로 지시하지 않고 의료진에게 확인하도록 한 수정안을 더 보수적이고 안전하다고 재판정했습니다. |
| baby-fever-threshold.en | PASS | PASS | 0 | - |
| baby-fever-threshold.es | PASS | PASS | 0 | - |
| baby-fever-threshold.ko | PASS | PASS | 0 | - |
| baby-formula-refusal-cold.en | PASS | PASS | 0 | - |
| baby-formula-refusal-cold.es | PASS | PASS | 0 | - |
| baby-formula-refusal-cold.ko | PASS | PASS | 0 | - |
| infant-cold-vomiting-feeding.en | PASS | PASS | 0 | - |
| infant-cold-vomiting-feeding.es | PASS | PASS | 0 | - |
| infant-cold-vomiting-feeding.ko | PASS | PASS | 0 | - |
| infant-wheezing-pneumonia-antibiotics.en | PASS | PASS | 0 | - |
| infant-wheezing-pneumonia-antibiotics.es | PASS | PASS | 0 | - |
| infant-wheezing-pneumonia-antibiotics.ko | PASS | PASS | 1 | - |
| influenza-a-high-fever-management.en | PASS | PASS | 0 | - |
| influenza-a-high-fever-management.es | PASS | PASS | 0 | - |
| influenza-a-high-fever-management.ko | PASS | PASS | 0 | - |
| mycoplasma-pneumonia-fever-reassessment.en | PASS | PASS | 0 | - |
| mycoplasma-pneumonia-fever-reassessment.es | PASS | PASS | 0 | - |
| mycoplasma-pneumonia-fever-reassessment.ko | PASS | PASS | 0 | - |
| pediatric-fever-alternating-meds.en | PASS | FAIL | 1 | 2차 Gemini가 중이염 항생제 지침의 생략만으로 해열제 교차 복용 영상이 안전하지 않다고 볼 근거는 없다고 재판정했습니다. 영상은 항생제 중단을 권하지 않습니다. |
| pediatric-fever-alternating-meds.es | PASS | PASS | 0 | - |
| pediatric-fever-alternating-meds.ko | PASS | PASS | 0 | - |
| pediatric-fever-sleep.en | PASS | PASS | 0 | - |
| pediatric-fever-sleep.es | PASS | PASS | 0 | 2차 Gemini가 원문의 수면 시간에 따른 안심 기준을 제거하고 깨우기 어려움·반응 저하 시 즉시 진료를 안내한 변경을 안전한 수정으로 판정했습니다. 1차 출처 충실도 WARN은 의학적 결함이 아닙니다. |
| pediatric-fever-sleep.ko | PASS | PASS | 0 | - |
| pediatric-tamiflu-dosing-flexibility.en | PASS | PASS | 0 | - |
| pediatric-tamiflu-dosing-flexibility.es | PASS | WARN | 1 | 2차 Gemini가 구토 후 추가 복용 전에 처방 의료진·약사에게 확인하도록 한 안내를 보수적이고 안전하다고 재판정했습니다. 원문의 일률적 1시간 재투여는 오셀타미비르 약물별 30분 기준과 상충합니다. |
| pediatric-tamiflu-dosing-flexibility.ko | PASS | PASS | 1 | 새 영상의 오셀타미비르 구토 후 30분 기준은 약물별 지침에 부합하며, 원문 블로그의 일률적 1시간 기준보다 안전하다고 2차 Gemini가 재판정했습니다. |
| persistent-nasal-congestion-reassessment.en | PASS | PASS | 0 | - |
| persistent-nasal-congestion-reassessment.es | PASS | PASS | 0 | - |
| persistent-nasal-congestion-reassessment.ko | PASS | PASS | 0 | - |
| powdered-fever-reducer-premix.en | PASS | PASS | 0 | - |
| powdered-fever-reducer-premix.es | PASS | PASS | 0 | - |
| powdered-fever-reducer-premix.ko | PASS | PASS | 0 | - |

개별 원문 Gemini 답변은 `raw/`에, 전체 답변 모음은 `gemini_answers.md`에 있습니다.
