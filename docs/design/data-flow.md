# Data & API Flow Design

## DB Schema (Projects)
| Column        | Type        | Notes |
|---------------|-------------|-------|
| id            | UUID / BIGINT | Primary key. |
| name          | TEXT        | 사용자 요청에 나온 프로젝트/별칭. Unique. |
| movie_title   | TEXT        | 영화 API에서 받은 정식 제목. |
| distributor   | TEXT        | 배급사 이름. |
| release_date  | DATE        | ISO `YYYY-MM-DD`. 예정/확정일 모두 포함. |
| director      | TEXT        | 감독 이름. 복수 감독 시 콤마 구분. |
| cast          | TEXT        | 주요 출연진 목록(콤마 구분). |
| genre         | TEXT        | 주 장르. 복합 장르 시 슬래시/콤마 구분. |
| dday_label    | TEXT        | `D-10`, `D-DAY` 등 문자열 캐시. |
| source        | TEXT        | 영화 API 출처(TMDB 등). |
| external_id   | TEXT        | 영화 API 고유 ID. Unique with source. |
| is_re_release | BOOLEAN     | 재개봉 여부. |
| last_updated  | TIMESTAMP   | 자동 갱신. |

### Index/Constraint Strategy
- `name` unique: 모든 사용자가 동일 프로젝트 이름으로 접근 시 중복 방지.
- `(source, external_id)` unique: 영화 원본 기준 중복 차단.
- Index on `release_date` for sorting upcoming events.

### Repository Interface (`app/db.py`)
```python
class ProjectRepository:
    def get_by_name(self, session, name: str) -> Project | None: ...
    def create(
        self,
        session,
        *,
        name,
        movie_title,
        distributor,
        release_date,
        director,
        cast,
        genre,
        dday_label,
        source,
        external_id,
        is_re_release,
    ) -> Project: ...
    def list_upcoming(self, session, today: date) -> list[Project]: ...
```
SQLAlchemy model definitions live in `app/models.py` with metadata for migrations.

## FastAPI & LLM Orchestration Flow
1. **Endpoint** `POST /dday`
   - Request body: `{ "query": "프로젝트 헤일메리 개봉일 디데이 설정" }`.
   - Validate payload, normalize query string.

2. **Service Flow**
   - Repository `get_by_name` (normalized title). If found → respond immediately with stored data.
   - If not found:
     1. Send conversation to LLM with system/dev prompts from `tool-prompt.md`.
     2. LLM may call `movie_search` tool → FastAPI server proxies to actual movie API or mock.
     3. Validate tool response (future release priority). If release past & no re-release → respond with "생성 불가" status, no DB insert.
     4. If valid future date:
        - Calculate `dday_label` from release date.
        - `ProjectRepository.create(...)` to persist.
        - Return success response (movie info + dday).

3. **Response Payloads**
```json
// success
{
  "name": "프로젝트 헤일메리",
  "movie_title": "프로젝트 헤일메리",
  "release_date": "2026-03-20",
  "dday": "D-30",
  "shared": true
}

// already exists
{
  "name": "프로젝트 헤일메리",
  "message": "이미 등록된 개봉일입니다. 지금은 D-30을 함께 기다리고 있어요.",
  "dday": "D-30"
}

// cannot create
{
  "name": "프로젝트 헤일메리",
  "message": "예정된 개봉일이 없어 D-Day를 만들 수 없어요. 재개봉 일정이 생기면 다시 알려주세요."
}
```

## Additional Notes
- Background worker can refresh D-Day labels daily using `release_date` difference to keep cached `dday_label` accurate.
- When LLM receives user-provided release date, compare with tool data before saving; if mismatch, prompt user and delay DB insert until confirmed.
