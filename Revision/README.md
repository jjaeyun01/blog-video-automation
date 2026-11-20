# FeverCoach FAIL 피드백 수정본

- 대상: 제출된 두 피드백 기록에서 Sam 검토자가 `F`로 판정한 46개 항목
- 중복 제출 및 동일 주제를 합친 결과: 13개 블로그 주제 × KO/EN/ES = 39개 수정 영상
- 완성 영상: [`videos/`](videos/)
- 피드백 파일명과 완성 영상 대응표, 원본·수정본 해시, 기술 검사 결과: [`revision_manifest.json`](revision_manifest.json)

원본 `jobs/` 영상은 수정하지 않았습니다. 이 폴더에는 수정 작업용 설정·장면·음성도 함께 보관되어 있습니다. 최종 배포용 파일은 `videos/`의 MP4입니다.

39개 모두 원본과 다른 MP4이며 1080×1920 세로 영상, 약 60초, H.264/AAC 스트림을 확인했습니다. 저장된 대본과 자막 텍스트 일치, 자막 이미지의 투명한 모서리도 검사했습니다.

2026-09-22 비통과 8편을 재생성하고 전편 Gemini 의학·시청각 재감사 및 저장된 MP4 해시 대조를 다시 진행했습니다. 현재 자동 선별 판정은 **39편 모두 PASS**입니다. [편별 최종 보고서](final_audit/final_pass_report.md), [Gemini 원문 답변 모음](final_audit/gemini_answers.md), [기계 판독용 상세 결과](final_audit/final_pass_manifest.json)를 확인할 수 있습니다. 교체 전 8편과 수정 작업 기록은 [`pass_repair/`](pass_repair/)에 보관했습니다. 이 PASS는 의사의 최종 승인을 대체하지 않습니다.
