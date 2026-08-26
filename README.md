# FeverCoach AI Shorts

매주 달라지는 소아 건강 블로그 글과 캐릭터 이미지 한 장을 입력해 60초 세로형
YouTube Shorts/Reels 영상을 만드는 Python 파이프라인입니다.

## 처리 흐름

1. 블로그 URL 또는 Markdown 원문을 읽습니다.
2. Gemini가 글의 의료 주장·수치·경고 신호를 추출하고 공통 10개 씬(각 6초)을 설계합니다.
3. 각 씬 내용에 맞춘 텍스트 없는 9:16 의료 참고 이미지를 Gemini가 만들고 캐릭터는 필요한 2~4개 씬에만 사용합니다.
4. Veo는 참고 이미지에서 한 가지 동작만 수행하며, 고정 카메라 또는 8% 이하의 느린 푸시인만 사용합니다.
5. 정확한 온도·시간·용량·화살표는 생성형 영상에 맡기지 않고 코드가 언어별 오버레이로 그립니다.
6. 동일한 영상 클립을 세 언어가 공유하고, 한국어·스페인어·영어 TTS를 각각 정확한 60초 타임라인에 맞춥니다.
7. TTS 문장을 1~3개 짧은 자막으로 나눠 순서대로 표시합니다. 문구가 조금이라도 다르면 전체 TTS 문장으로 자동 복구합니다.

## 설치

Python 3.11 이상과 FFmpeg가 필요합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
brew install ffmpeg
cp .env.example .env
```

`.env`에 `GEMINI_API_KEY`를 입력합니다. ElevenLabs를 사용하려면 관련 키와
Voice ID도 설정합니다.

참고 이미지 모델은 `.env`의 `GEMINI_IMAGE_MODEL`로 바꿀 수 있습니다. 기본값은
`gemini-3.1-flash-image`입니다.

## 매주 실행

캐릭터 이미지를 `inputs/`에 넣고 블로그에서 제작 설정을 만듭니다.

```bash
fevercoach-shorts plan \
  --url "https://www.fevercoach.us/ko/post/..." \
  --character-image inputs/this_week_character.png \
  --output inputs/this_week.production.json
```

기본값으로 아래 세 파일이 한 번에 생성됩니다. 영상 장면과 영문 Veo 프롬프트는
공유되고, 제목·내레이션·자막·고지 문구만 자연스럽게 현지화됩니다.

```text
inputs/this_week.production.ko.json
inputs/this_week.production.es.json
inputs/this_week.production.en.json
```

일부 언어만 필요하면 `--languages ko en`처럼 지정할 수 있습니다.

URL 대신 정리한 원고 파일도 사용할 수 있습니다.

```bash
fevercoach-shorts plan \
  --article-file inputs/this_week.md \
  --character-image inputs/this_week_character.png \
  --output inputs/this_week.production.json
```

생성 비용을 쓰기 전에 씬, 프롬프트, 경로와 60초 구성을 확인합니다.

```bash
fevercoach-shorts build \
  --config \
    inputs/this_week.production.ko.json \
    inputs/this_week.production.es.json \
    inputs/this_week.production.en.json \
  --plan-only
```

검토한 JSON으로 전체 영상을 만듭니다.

```bash
fevercoach-shorts build \
  --config \
    inputs/this_week.production.ko.json \
    inputs/this_week.production.es.json \
    inputs/this_week.production.en.json \
  --tts-provider gemini
```

ElevenLabs를 쓰려면 `--tts-provider elevenlabs`로 변경합니다. 영상 클립까지만
생성하려면 `--clips-only`를 사용합니다.

```bash
fevercoach-shorts status --config inputs/this_week.production.ko.json
```

## 출력

```text
jobs/{slug}/
├── visuals/                   # 세 언어가 공유하는 Veo 작업과 원본 클립
│   ├── generation_plan.json
│   ├── operations.json
│   ├── assets/                    # 글 내용별로 자동 생성한 장면 참고 이미지
│   └── clips/
├── ko/                        # 한국어 TTS·자막·최종 영상
│   └── final_shorts.mp4
├── es/                        # 스페인어 TTS·자막·최종 영상
│   └── final_shorts.mp4
└── en/                        # 영어 TTS·자막·최종 영상
    └── final_shorts.mp4
```

세 언어는 `visuals/`의 동일한 참고 이미지와 Veo 클립을 재사용하므로 영상 생성 요청은 한 세트만
발생합니다. 동일 명령을 다시 실행하면 완료된 Veo/TTS 결과를 재사용합니다. 프롬프트나 캐릭터
이미지가 변경된 씬만 새 지문을 갖기 때문에 해당 씬만 다시 요청됩니다.
Veo가 일시적인 과부하 코드(예: `14: high demand`)를 반환하면 10초 간격으로
해당 씬만 최대 5회 자동 재제출합니다. 기본 모델의 재시도를 모두 소진하면
완료되지 않은 씬만 `GEMINI_VIDEO_FALLBACK_MODEL`의 Fast 모델로 전환합니다.
TTS가 씬 길이를 조금 넘으면 자연스러운 범위에서 자동으로 속도를 조정하고,
짧으면 뒤를 무음으로 채워 편집 타임라인을 정확히 유지합니다.

## OC43 예제

[`examples/oc43.production.json`](examples/oc43.production.json)은 6개 씬과 60초
타임라인이 완성된 예제입니다. `inputs/oc43_character.png`만 추가하면
`--plan-only` 검증 또는 실제 빌드에 사용할 수 있습니다.

## 주의사항

- 생성된 의료 콘텐츠는 게시 전 의료진 검수가 필요합니다.
- Q&A 글에서는 질문자의 추측·전해 들은 기준을 의료 권고로 사용하지 않고, 의료진 답변이
  명시적으로 확인한 내용만 장면 주장과 수치로 사용합니다.
- 약 용량은 원문이 정확히 제공할 때만 표시하며, 질량을 부피로 임의 변환하지 않습니다.
  용량 장면은 주방 숟가락 대신 보정된 투약 기구나 디지털 저울을 사용합니다.
- 처방약 중단·확정적 진단 문구는 기획 프롬프트와 빌드 전 안전 검사에서 차단합니다.
- Veo가 프롬프트를 무시하고 다른 언어 대사를 생성할 수 있으므로 Veo 원본 오디오는
  완전히 제거하고 각 언어 TTS만 사용합니다.
- 개별 `dubbed_clips`에도 해당 씬의 언어별 TTS만 넣습니다.
- API 모델명은 변경될 수 있으므로 `.env`의 `GEMINI_VIDEO_MODEL`로 교체할 수 있습니다.
