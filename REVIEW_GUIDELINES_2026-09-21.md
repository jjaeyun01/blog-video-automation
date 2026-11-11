# Week 8 추가 리뷰 반영: 파이프라인 규칙

기준 버전: `2026-09-21.week8-10-31.v3`. [기존 9월 13일 기준](REVIEW_GUIDELINES_2026-09-13.md)에 추가 적용한다.

입력은 [사용자 리뷰 원문](/Users/jaeyoonlee/.codex/attachments/d02c228f-9558-42b8-9d3a-513da01c814d/pasted-text.txt)의 **60개 파일·120개 리뷰(MC 60, Sam 60)**다. Sam 판정은 F 30개·P 30개다. 파일 번호와 언어가 같은 주제를 가리키지 않는 행이 있다. 예를 들어 `week8-English-25`는 기침, KO/ES-25는 구토 후 수유이다. 따라서 파일 번호를 주제 ID로 쓰지 않고, 각 영상의 실제 내용·언어·블로그 원문과 연결해 검토한다. P도 개선 노트가 있으므로 자동으로 무시하지 않는다.

| 피드백 주제 | 생성 전 대본·화면 기준 | 최종 검수 기준 |
|---|---|
| 해열제 | 두 약 동시투여를 권하지 않음. 불편감이 있으면 단일 약 우선. 교차 투여는 약별 간격·하루 총량·기록이 있는 계획으로 제한. 6개월 미만 이부프로펜 자가투여 제한을 모든 언어에 유지 | 2–3시간이라는 간격만으로 자동 FAIL을 만들지 않음. 약명·농도·체중이 맞으면 제시된 mL 용량을 계산해 검토. 40–41kg 예시를 영아에게 일반화한 그림은 오류 |
| 약 조제·재복용 | 가루약의 보관시간·냉장 여부는 제품/약사 지시를 따름. 장운동 조절약 등 이름 없는 처방약을 증상만 보고 중단·재개하도록 하지 않음 | 과거 오셀타미비르 30분 전/후 구토 지침은 해당 약에만 적용. 하루 묽은 변 3회만으로 모든 아이를 응급실로 보내지 않음 |
| 영아 수유·구토 | ‘12시간 수유 거부 후 진료’를 보편 기준으로 쓰지 않음. 거의 못 먹음, 소변 감소, 처짐은 더 일찍 평가. 분유는 **제품 표시대로 정상 농도**, 필요한 경우 **1회 먹이는 양**을 조절. 이유식 대기와 모유/분유·수분 공급은 구분 | 젖병에 액체를 떨어뜨려 분유를 묽게 만드는 듯한 연출, 모든 영아에게 고정 30–50mL/30분, 머리·몸통 지지 없는 수유를 잡음. ‘2/3’가 실제 희석 지시라고 근거 없이 단정하지 않음 |
| 영아 체온·수면 | ‘어른보다 한 겹 적게’를 일반 규칙으로 쓰지 않음. 손발의 온도만으로 순환·안전을 보장하지 않음. 영아의 잠자리에는 베개·푹신한 둘레·느슨한 이불 없음 | 옷차림 문구와 수면 그림을 별도 검사. 저체온증·질식이 실제 발생했다는 주장 없이 위험한 시범으로 기술 |
| 코세척 | 누운 아이의 젖힌 머리에 세척병을 대는 장면 금지. 협조 가능한 큰 아이의 적절한 자세와 영아의 식염수 점적/부드러운 흡인을 구분. 세척액의 안전한 물과 기구 관리 확인 | 장기 코막힘에 CT를 보편 검사로 요구하지 않음. 영상만으로 실제 흡인 사고가 났다고 단정하지 않음 |
| RSV·폐렴·마이코플라즈마 | RSV는 열 없이 악화 가능. 퇴원 10일·3주 발열은 사례 경과일 수 있지만 보편적 대기 기준이 아님. 검사 종류·시점은 진찰에 따름. 마이코플라즈마 접촉만으로 예방적 항생제 지시하지 않음 | 새 발열·노란 콧물만으로 세균 감염 확진 금지. 호전된 단순 폐렴에서 일률적 추적 X-ray도 요구하지 않음. 이미 처방된 검사를 임의 취소하지 않음. 마른기침 하나로 진단하지 않음 |
| 기타 장면 | 두피 혹을 혈종/두개강 내 출혈로 단정하지 않음. 가습기 청결을 설명. 항생제는 기침을 직접 억제하는 약처럼 묘사하지 않음 | 치료 효과 시간·멍 소실일을 보장하지 않음. 스포츠음료와 경구수분보충액을 동등하게 취급하지 않음 |

검수는 각 언어의 실제 최종 영상, 실제 발화, 화면 자막, 원문과 그림을 비교한다. `src/fevercoach_shorts/review_rules.py`의 공통 규칙은 기획·일괄검사·최종검수·재생성 프롬프트에 들어간다. 명백한 위험 문구와 시범은 `src/fevercoach_shorts/safety.py`에서 영상 생성 전에 막는다. 그림 생성과 Veo 보정 프롬프트도 수면·수유·코세척의 자세를 명시한다. 기존 검수 결과는 가이드라인 버전이 바뀌어 그대로 PASS로 재사용되지 않는다.

의학적 근거 확인: [NICE 해열제 지침](https://www.nice.org.uk/guidance/ng143/chapter/recommendations), [AAP 이부프로펜 연령](https://www.healthychildren.org/English/safety-prevention/at-home/medication-safety/Pages/Ibuprofen-for-Fever-and-Pain.aspx), [CDC 분유 조제](https://www.cdc.gov/infant-toddler-nutrition/formula-feeding/preparation-and-storage.html), [FDA 코세척](https://www.fda.gov/consumers/consumer-updates/rinsing-your-sinuses-neti-pots-safe), [CDC RSV](https://www.cdc.gov/rsv/infants-young-children/index.html), [CDC 마이코플라즈마](https://www.cdc.gov/mycoplasma/about/index.html), [Medicines for Children 가루약](https://www.medicinesforchildren.org.uk/advice-guides/giving-medicines/how-to-give-medicines-granules-and-powders/). 확인일: 2026-09-21. 이 자료들은 생성 규칙의 안전 기준이며 각 블로그 글의 출처와 구분한다.
