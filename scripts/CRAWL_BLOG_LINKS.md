# FeverCoach 한국어·영어·스페인어 블로그 링크 수집

프로젝트 루트에서 실행:

```bash
.venv/bin/python scripts/crawl_fevercoach_blog.py --output-dir outputs/blog_links

# 영어 / 스페인어 (각각 별도 폴더에 저장)
.venv/bin/python scripts/crawl_fevercoach_blog.py --language en --output-dir outputs/blog_links_en
.venv/bin/python scripts/crawl_fevercoach_blog.py --language es --output-dir outputs/blog_links_es
```

- `--language ko|en|es`로 언어를 선택한다(기본 ko). 선택 언어의 사이트맵 및 하위 사이트맵을 순회한다.
- 목록 페이지의 링크·HTML 페이지 이동도 확인한다. KO는 `/ko/post/…`, EN은 `/post/…`, ES는 `/es/post/…`만 저장해 언어 경로가 섞이지 않는다.
- 선택 언어의 실제 URL을 수집하며, 한국어 URL에 언어 접두사를 붙여 번역 링크를 추측하지 않는다. 본문 언어 판별이나 언어별 글 대응 매칭은 하지 않는다.
- URL 인코딩, 추적 파라미터, 앵커 차이를 정규화해 중복 제거한다.
- 동일 출처 HTTPS만 요청하며 외부 사이트맵/외부 리다이렉트는 따라가지 않는다.
- 기본 요청 간격 0.5초, 타임아웃 30초. 재시도 및 최대 순회 제한이 있다.
- 공지사항도 포함한다. 공개 사이트맵에 없고 HTML에도 없는 글까지 보장하지는 않는다.
- 기사 본문, 영상 생성, Gemini 호출은 수행하지 않는다.

출력:

- `blog_links.txt`: 한 줄에 URL 하나. URL은 브라우저/스크립트에서 사용할 수 있게 인코딩되어 있다.
- `blog_links.json`: URL, 읽기 쉬운 한글 slug, 제목(확인된 경우), 최종 수정일, 발견 출처, 수집 경고.

제목은 URL에서 추측하지 않는다. 기본 실행에서 목록에 노출되지 않은 글의 `title`은 `null`이다.
모든 글의 실제 제목도 필요하면 `--fetch-titles`를 추가한다(글마다 추가 요청이 발생).

```bash
# 소규모 제목 수집 테스트: URL 정렬 기준 앞 5개, 최신순이 아님
.venv/bin/python scripts/crawl_fevercoach_blog.py --fetch-titles --limit 5 --output-dir outputs/blog_links_sample
```

같은 출력 경로가 이미 존재하면 덮어쓰지 않고 중단한다. 의도적으로 갱신할 때만 `--overwrite`를 사용한다.
일부 사이트맵/페이지가 실패하면 확보한 결과를 `status=partial` 및 경고와 함께 저장하고 종료 코드 2를 반환한다.
성공은 0, 접근 불가/링크 0건은 1이다. `--limit`로 일부만 내보내면 `limited=true`로 표시한다.
`status=ok`는 발견 경로를 오류 없이 읽었다는 뜻이지, 모든 글의 접근 가능성이나 완전성을 보증하지 않는다.
