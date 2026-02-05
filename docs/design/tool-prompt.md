# LLM Tool & Prompt Design

## 영화 검색 툴 인터페이스
- **식별자**: `movie_search`
- **설명**: 영화 제목을 받아 개봉일과 기본 정보를 반환. D-Day 계산과 사용자 피드백에 사용.
- **요청 필드**
  - `title` *(string, required)*: 사용자 요청에서 추출한 영화/프로젝트 명.
  - `year` *(integer, optional)*: 사용자가 특정 연도를 언급하거나 재개봉 확인이 필요할 때 전달.
  - `country` *(string, optional)*: 국가 코드(예: `KR`, `US`). 사용자 입력이나 선호도에 따라 필터링.
- **응답 필드**
  - `title`: 정식 영화 제목.
  - `release_date`: ISO8601 `YYYY-MM-DD` 형식의 개봉일.
  - `overview`: 사용자에게 공유할 간단 설명.
  - `external_id`: 원본 API 식별자(TMDB/KOBIS 등).
  - `country`: 개봉 국가 코드 또는 이름.
  - `is_re_release`: 재개봉 여부(boolean). 없을 경우 `false`로 간주.
  - `source`: 데이터 출처 문자열.
- **에러 규약**
  - 404 → 영화 미발견. LLM은 사용자에게 다른 제목/연도를 요청.
  - 409 → 동일 제목 다수. 추가 필터(연도/국가)가 필요하다는 메시지 포함.
  - 5xx/네트워크 → LLM이 사과하고 나중에 다시 시도하라고 안내.
- **샘플 호출**
```json
{
  "title": "프로젝트 헤일메리",
  "year": 2026,
  "country": "KR"
}
```
- **샘플 응답**
```json
{
  "title": "프로젝트 헤일메리",
  "release_date": "2026-03-20",
  "overview": "우주 이상 현상을 추적하는 임무를 맡은 크루의 이야기",
  "external_id": "tmdb:123456",
  "country": "KR",
  "is_re_release": false,
  "source": "TMDB"
}
```

## LLM 프롬프트 구조
1. **System Message**
   - 역할: "FastAPI 기반 D-Day 비서"임을 정의.
   - 핵심 지침:
     - 사용자는 모두 같은 개봉일을 기다리므로 기존 레코드 조회를 우선 수행.
     - 영화 개봉일이 미래일 때만 D-Day를 생성하고, 모든 일정이 과거면 재개봉 확인 후 없으면 중단.
     - 사용자 제공 개봉일은 툴 결과와 비교해 차이를 설명하고 확인 요청.
     - 성공 시 DB에 자동 저장됨을 전제로 응답 구성.

2. **Developer Message / Tool Instructions**
   - 툴 호출 조건: 영화명 또는 프로젝트명이 명확하고 기존 DB에 없을 때.
   - 툴 응답 처리: 미래 개봉일 우선, `is_re_release` true면 재개봉임을 명시.
   - 오류 대응: 404/409/5xx 상황별 사용자 안내 스크립트 포함.

3. **Conversation Template**
   - **사용자**: "프로젝트 헤일메리 개봉일 디데이 설정"
   - **Assistant(내부 추론)**: 기존 `projects` 조회 → 없으므로 툴 호출 준비.
   - **Tool Call Payload**: 위 샘플 JSON.
   - **Tool Result**: 샘플 응답.
   - **Assistant 응답**: "프로젝트 헤일메리은 2026-03-20 개봉 예정이라 현재 D-30입니다."

4. **Fallback 예시**
   - 모든 개봉일이 과거 & 재개봉 없음 → "현재 예정된 개봉이 없어 D-Day를 만들 수 없어요."
   - 사용자 제공 날짜와 검색 결과 불일치 → 둘 다 제시하고 원하는 날짜를 재확인.

이 설계를 기준으로 LLM 오케스트레이션 계층에서 시스템/도우미 메시지를 구성하고, 툴 함수를 메타데이터(Function Calling schema 등)로 등록하면 됩니다. 실제 구현은 LangChain의 `ChatOpenAI`와 `StructuredTool` 조합으로 위 정의를 그대로 코드에 옮겨, 추후 LangSmith에서 호출 이력을 추적할 수 있게 준비되어 있습니다.
