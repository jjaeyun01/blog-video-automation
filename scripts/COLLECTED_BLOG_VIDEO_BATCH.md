# 수집한 글의 언어별 쇼츠 제작

현재 배치: `outputs/collected_blog_videos_2026-10-10`.

## 실패 분석 및 원인별 재시도

`python scripts/run_collected_blog_videos.py analyze`는 `failure_analysis.json`에 원인별 집계와 항목별 오류를 저장한다.
`python -u scripts/run_collected_blog_videos.py run --retry-failed`는 연결 사전 검사 후 실패 항목을 원인별로 처리한다.
네트워크·빈 생성 결과는 기존 유효 캐시를 재사용하여 재시도한다. TTS 길이·참조 이미지·기획 검증 오류는 이전 오류를 전달해 원문 기반으로 재기획한다. 변경 전 설정은 `retry_backups/`에 보존한다.
알 수 없는 오류·인증/할당량 오류는 자동 재시도에서 보류한다. 항목별 누적 재시도는 최대 3회이며 `retry_history`에 이전 원인을 남긴다.
연속 네트워크 실패 3회는 `BLOCKED_NETWORK`, 여유 공간 8GB 미만은 `BLOCKED_DISK`로 중단한다. 한 실행에서 각 대상은 한 번만 재시도하며, PASS는 해시와 최신 검수를 확인해 건너뛴다. 의학 오류의 해결이나 최종 PASS를 보장하지 않는다.

한국어 1,060개, 영어 1,158개, 스페인어 1,094개 URL을 각각 해당 언어의 영상으로 만든다(총 3,312편).
언어별로 최종 수정일 내림차순 정렬하고 KO→EN→ES 순서로 교차 실행한다.
공지사항을 포함한 크롤링 원본 전체가 입력이며, 기획 검증에 실패하는 원문은 실패 사유를 남긴다.

```bash
# 수집 결과를 고정된 제작 목록으로 저장(기존 목록은 보존)
.venv/bin/python scripts/run_collected_blog_videos.py prepare

# 제작 및 이어서 실행
.venv/bin/python -u scripts/run_collected_blog_videos.py run

# 진행 상태
.venv/bin/python scripts/run_collected_blog_videos.py status

# 실패 항목도 다시 시도
.venv/bin/python -u scripts/run_collected_blog_videos.py run --retry-failed
```

기존 `ScenePlanner.create_multilingual`에 **한 개 언어만** 전달하고 `ShortsPipeline.build`로 생성한다.
URL+언어에서 고정된 내부 작업 키를 만들어 서로 다른 글/언어의 영상 캐시가 섞이지 않게 한다.
기존 Gemini Kore TTS, 투명 배경 자막, 60초 길이 및 장면별 의학 검수·수정 기능을 사용한다.
기획이 장면 수·캐릭터 등장 수 등 로컬 검증에 실패하면 오류를 전달해 최대 3회 재기획한다.
실제 참고 이미지에 생성된 숫자·글자 또는 높은 의학적 위험이 있으면 Veo 호출 전에 해당 이미지부터 재생성·재검사한다.
영상 프롬프트 보정 캐시 버전은 6이다.

- `manifest.json`: 고정된 원본 링크 목록과 수집 파일 해시.
- `status.json`: 현재 작업, 단계, 성공·실패·대기 개수와 오류.
- `sources/`: 제작 시 읽은 실제 제목과 원문.
- `configs/`: 언어별 제작 설정.
- `jobs/`: 이미지, Veo 작업 ID·클립, TTS, 렌더링, Gemini 감사·수정 내역.
- `completed/ko`, `completed/en`, `completed/es`: 현재 검수 버전·모델의 PASS 및 영상 해시가 확인된 최종본.
- `errors/`: 실패 원인. API 키는 기록에서 가린다.

완성 파일명은 실제 영상 제목 + URL 식별자 8자리 + `_KO`, `_EN`, `_ES`다.
`completed/`에는 MP4만 저장한다. `.audit.json`과 `.delivery.json`은 같은 언어별 구조와 파일명으로 `delivery_records/`에 보존한다. 기존 혼합 폴더는 `python scripts/run_collected_blog_videos.py organize`로 정리할 수 있으며, 활성 작업이 있으면 잠금으로 정리를 차단한다.
같은 파일시스템에서는 하드링크를 사용해 작업 영상과 납품 영상의 중복 저장을 줄인다.
작업 중 결과의 WARN/FAIL을 PASS로 취급하지 않는다.
동일 배치의 워커는 파일 잠금으로 하나만 실행한다.

기본 여유 공간 하한은 8GB다. 공간이 부족하면 `BLOCKED_DISK`, API 인증·할당량·결제·모델 접근 문제가 발생하면
`BLOCKED_API`로 기록하고 신규 작업을 멈춘다. 원인이 해소된 뒤 같은 명령으로 재개한다.
`--max-items N`으로 한 번 실행할 작업 수를 제한할 수 있다.
컴퓨터 종료나 실행 세션 종료 후에는 같은 실행 명령으로 저장된 작업부터 이어간다.
의학적 또는 영상 품질 실패로 보류된 항목은 `--retry-failed`로 명시적으로 재시도한다.
수천 편 전체 제작에는 API 사용량과 충분한 저장 공간이 필요하다.
