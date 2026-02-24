# WAITWITH D-Day Service

WAITWITH은 "함께 기다리는 경험"에 집중한 AI 기반 D-Day 공유 서비스입니다. 혼자 기대하며 기다리는 대신, 사람들이 같은 작품의 개봉을 함께 카운트다운하면서 소통할 수 있도록 기획했습니다. 기존 캘린더나 알림 앱은 개인 일정 위주라 "같이 기다리는" 감정을 나누기 어려웠고, 영화/드라마 개봉일 정보도 여러 커뮤니티에 흩어져 있어 통합된 경험이 부족했습니다. WAITWITH는 LLM이 개봉일을 자동 검색+검증하고, 그 결과를 공유 카드와 채팅 흐름으로 풀어줘 "같이 기다리는 커뮤니티"를 구현하는 것이 목표입니다.

## 기획 의도 & 문제 인식
- **문제**: 새로운 영화/드라마 개봉 소식을 나만 알고 있다가 잊어버리거나, 커뮤니티 게시글에 의존하는 경우가 많음. 또한 "다 같이 기다리는" 감정은 댓글 기반 커뮤니티나 단발성 게시글에서 흩어져 버림.
- **의도**: 채팅으로 작품 이름만 불러도 AI가 자동으로 개봉일을 찾아 D-Day로 기록하고, 누구나 공유 카드에서 같은 작품을 기다리는 사람 수/정보를 확인하게 해 "함께 기다림"을 서비스화.
- **콘셉트**: 대기열(Waiting Room) + 디데이 → WAITWITH. 채팅-카드-커뮤니티 UX를 하나로 묶어서 “기대되는 작품을 함께 기다리는 장소”를 구축.

## 기술 스택
- **Backend**: FastAPI, SQLAlchemy, httpx, LangChain/OpenAI, TMDb API
- **Frontend**: React + Vite + TypeScript, CSS Grid/Flexbox
- **Infra/Tools**: SQLite(dev), uvicorn, pytest, docs/design 가이드, REST Client(requests.http)

## 핵심 특징
- **채팅형 오케스트레이션**: `/chat/stream` SSE가 `analysis → tool_started → tool_result → token → final` 이벤트를 스트리밍하고, 프런트는 각 단계별 피드백을 채팅 버블 아래에서 보여줍니다.
- **영화/드라마 통합 검색**: TMDb의 movie/tv API를 모두 사용해 `content_type`으로 구분 저장하며, 드라마도 영화와 동일한 UX로 공유 가능합니다.
- **공유 대기실 & 카드 UI**: `/dday` REST API로 저장된 프로젝트는 React 대시보드의 카드 형태로 노출되며, “같이 기다려요” 버튼을 통한 커뮤니티 액션을 실험할 수 있습니다.
- **확장 지향 설계**: `tool_registry`에 StructuredTool을 추가하면 LLM 프롬프트만으로 확장 가능하고, docs/design에 데이터 플로우/프런트 스타일 가이드가 정리돼 협업을 돕습니다.

## 디렉터리 구조
```
app/                # FastAPI, LangChain 오케스트레이터, TMDb 클라이언트
frontend/           # React + Vite UI
docs/design/        # 데이터 플로우, 프론트 설계 문서
requests.http       # REST/SSE 수동 테스트용 스크립트
```

## 백엔드 실행
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # TMDB_API_KEY, OPENAI_API_KEY 등 설정
echo "DATABASE_URL=sqlite:///./dday.db" >> .env
uvicorn app.main:app --reload
```
주요 환경 변수 (`app/core/config.py` 참고):
- `TMDB_API_KEY`, `TMDB_REGION`, `TMDB_LANGUAGE`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY` (선택)

## 프런트 실행
```bash
cd frontend
npm install
npm run dev  # http://localhost:5173 접속, 프록시로 백엔드를 호출
```

## API 요약
- `POST /dday`: LangChain 툴을 실행해 프로젝트 생성/조회.
- `GET /dday`: 공유 디데이 카드 목록.
- `GET /dday/longest`: 가장 멀리 있는 개봉일.
- `POST /chat/stream`: SSE 채팅 엔드포인트. `start → analysis → tool_started → tool_result → dday → token → assistant_message → end` 순으로 이벤트가 발생합니다.

`requests.http` 예시:
```http
### 디데이 생성/조회
POST http://localhost:8000/dday
Content-Type: application/json
{"query": "듄 파트 3 개봉일"}

### 채팅 SSE
POST http://localhost:8000/chat/stream
Content-Type: application/json
{"query": "28년 후 디데이 찾아줘"}
```

## 테스트
```bash
pytest tests/test_dday_service.py
```

## Roadmap
- Supabase Postgres/Auth 연동
- “같이 기다려요” 반응 카운트 저장 및 UI 반영
- 캘린더 내보내기, Slack/Discord 알림 연계
- 모바일 레이아웃 및 접근성 강화
