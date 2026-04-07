# travelPick Block Studio

FastAPI + SQLite 기반의 노션 스타일 블록 페이지 예시입니다.

기본 단위는 블록이며, 다음 인터페이스를 지원합니다.

- `text` 블록: 텍스트 문단/메모
- `image` 블록: 이미지 URL + 캡션
- `container` 블록: 여러 블록을 중첩해서 담는 구조

## 아키텍처

- 백엔드: FastAPI + Pydantic
- 저장소: SQLite (`data/blocks.sqlite3`)
- 프론트엔드: Vanilla JS 블록 렌더러

블록 데이터는 SQLite의 `documents`, `blocks` 테이블에 저장되며,
`parent_block_id`를 이용해 트리 형태로 문서를 구성합니다.

## 실행 방법

```bash
uv sync
uvicorn main:app --reload
```

브라우저에서 `http://127.0.0.1:8000` 접속

앱 시작 시 DB 파일이 없으면 자동으로 생성되고, 예시 문서가 시드됩니다.

## API

- `GET /api/documents`: 문서 목록 조회
- `GET /api/documents/{document_id}`: 블록 트리 포함 문서 조회

응답 예시:

```json
{
	"id": "travel-pick-main",
	"title": "travelPick",
	"subtitle": "Notion base block page",
	"blocks": [
		{
			"id": "b-intro",
			"type": "container",
			"title": "소개",
			"layout": "vertical",
			"children": [
				{
					"id": "b-intro-text",
					"type": "text",
					"text": "travelPick는 여행 정보를 블록 단위로 조립해 문서처럼 관리하는 프로젝트입니다."
				}
			]
		}
	]
}
```

## 프로젝트 구조

```text
main.py
app/models/blocks.py
app/repositories/sqlite_blocks.py
data/blocks.sqlite3
templates/index.html
static/css/style.css
static/js/gallery.js
```

## Conventions

- Code: `docs/CODE_CONVENTION.md`
- GitHub: `.github/GITHUB_CONVENTION.md`
- Contribution Guide: `CONTRIBUTING.md`
