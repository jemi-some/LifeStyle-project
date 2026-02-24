# JWT 인증 트러블슈팅 기록

> Supabase + FastAPI 프로젝트를 Vercel에 배포하면서 겪은 JWT 인증 문제의 원인 분석과 해결 과정을 정리한 문서입니다.

---

## 1. JWT란 무엇인가?

**JWT(JSON Web Token)**는 두 시스템 사이에서 "이 사람은 인증된 사용자입니다"라는 정보를 안전하게 주고받기 위한 **디지털 증명서**입니다.

### JWT의 구조

JWT는 `.`으로 구분된 3개의 파트로 이루어져 있습니다:

```
eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV
|______ Header ______||________ Payload ________||____________ Signature ____________|
```

| 파트 | 역할 | 예시 내용 |
|:---|:---|:---|
| **Header** | 어떤 알고리즘으로 서명했는지 | `{"alg": "ES256", "typ": "JWT"}` |
| **Payload** | 사용자 정보 (누구인지) | `{"sub": "user-id-123", "email": "user@example.com"}` |
| **Signature** | 위조 방지 서명 | Header + Payload를 비밀키로 암호화한 결과 |

### 서명 알고리즘의 종류

| 알고리즘 | 방식 | 키 | 특징 |
|:---|:---|:---|:---|
| **HS256** | 대칭키 (Symmetric) | 하나의 Secret Key | 간단하지만 같은 키로 서명 + 검증 |
| **RS256** | 비대칭키 (Asymmetric) | Private Key + Public Key | 더 안전, Public Key만으로 검증 가능 |
| **ES256** | 비대칭키 (Asymmetric) | Private Key + Public Key | RS256과 유사, 더 짧은 키 사용 |

---

## 2. 우리 프로젝트에서 JWT를 사용한 이유

### 인증 흐름

```mermaid
sequenceDiagram
    participant U as 사용자 (브라우저)
    participant S as Supabase Auth
    participant F as FastAPI 백엔드

    U->>S: 1. 구글 로그인 요청
    S->>U: 2. JWT 토큰 발급 (access_token)
    U->>F: 3. API 요청 + Bearer Token
    F->>F: 4. 토큰 검증 → "이 사람 맞아?"
    F->>U: 5. 디데이 목록 응답
```

- **프론트엔드**: Supabase JS SDK로 구글 로그인 → JWT 토큰을 받음
- **백엔드**: 프론트엔드가 보낸 JWT 토큰을 검증하여 "누구의 요청인지" 파악

### 왜 백엔드에서 직접 검증했나?

백엔드(FastAPI)는 Supabase JS SDK를 쓸 수 없습니다 (파이썬이니까). 그래서 **PyJWT 라이브러리**로 토큰을 직접 해독(decode)하는 방식을 선택했습니다.

```python
# 초기 구현 (HS256 기반)
payload = jwt.decode(
    token,
    SUPABASE_JWT_SECRET,    # Supabase에서 제공하는 비밀키
    algorithms=["HS256"],   # 대칭키 알고리즘
    audience="authenticated"
)
```

이 방식은 **로컬 개발 환경에서는 완벽하게 동작**했습니다.

---

## 3. Vercel 배포 후 발생한 문제들

### 3-1. 첫 번째 에러: `The specified alg value is not allowed`

```
Invalid authentication credentials: The specified alg value is not allowed
```

**원인**: 코드는 `HS256`(대칭키)만 허용했지만, Supabase 프로젝트의 JWT가 실제로는 **`ES256`**(비대칭키)으로 서명되어 있었습니다.

```json
// 실제 JWT Header (디버깅으로 확인)
{
  "alg": "ES256",          // ← HS256이 아니라 ES256!
  "kid": "8b5851a9-...",
  "typ": "JWT"
}
```

**배경**: Supabase는 최근 보안 체계를 업그레이드하면서 기존의 `HS256` (Legacy JWT Secret) 방식에서 `ES256` (JWT Signing Keys) 방식으로 마이그레이션했습니다. 대시보드에서도 아래와 같은 안내 문구가 표시되고 있었습니다:

> "Legacy JWT secret has been migrated to new JWT Signing Keys"

---

### 3-2. 두 번째 에러: `Algorithm not supported`

```
Invalid authentication credentials: Algorithm not supported
```

**시도한 해결책**: `algorithms` 파라미터에 `ES256`을 추가

```python
payload = jwt.decode(
    token,
    SUPABASE_JWT_SECRET,
    algorithms=["HS256", "RS256", "ES256"],  # ES256 추가
    options={"verify_aud": False}
)
```

**실패 원인**: `ES256`은 비대칭키 알고리즘이므로, PyJWT가 이를 처리하려면 **`cryptography`** 라이브러리가 필요합니다. 하지만 Vercel의 서버리스 환경에 이 라이브러리가 설치되지 않고 있었습니다.

**추가 시도**:
- `requirements.txt`에 `cryptography`, `ecdsa` 추가
- `PyJWT[crypto]`로 변경 (crypto extras 포함)
- `pyproject.toml`에도 동일하게 추가
- `api/requirements.txt` 별도 생성

**결과**: Vercel 빌드 로그에서 계속 `Cryptography library NOT found` 메시지 출력. Vercel의 서버리스 빌드 환경에서 C 확장이 필요한 `cryptography` 라이브러리의 바이너리 호환 문제가 있었던 것으로 추정됩니다.

---

### 3-3. 세 번째 에러: JWKS 방식 시도 → `HTTP Error 401/404`

`cryptography` 설치가 안 되니, **JWKS(JSON Web Key Set)** 방식으로 우회를 시도했습니다. JWKS란 Supabase가 공개키를 제공하는 엔드포인트에서 자동으로 키를 가져오는 방식입니다.

```python
# JWKS 방식
jwks_url = f"{SUPABASE_URL}/auth/v1/jwks"
jwks_client = jwt.PyJWKClient(jwks_url)
signing_key = jwks_client.get_signing_key_from_jwt(token)

payload = jwt.decode(token, signing_key.key, algorithms=["ES256"])
```

**발생한 에러들**:

| 순서 | 에러 | 원인 |
|:---|:---|:---|
| 1 | `HTTP Error 401: Unauthorized` | Supabase JWKS 엔드포인트가 `apikey` 헤더를 요구 |
| 2 | `HTTP Error 404: Not Found` | JWKS URL이 잘못되었거나 (환경변수 누락), Supabase 버전에 따라 엔드포인트 경로가 다름 |
| 3 | `Algorithm not supported` | JWKS로 키를 받아와도 `cryptography` 없이는 ES256 디코딩 불가 |

**근본 원인**: `cryptography` 라이브러리가 없으면 JWKS 방식도 결국 `jwt.decode()`에서 ES256을 처리할 수 없으므로, 이 접근법 자체가 무의미했습니다.

---

## 4. 최종 해결: Supabase API 직접 호출 방식

### 발상의 전환

JWT를 "직접 해독"하는 것을 포기하고, **Supabase에게 대신 물어보는 방식**으로 전환했습니다.

```mermaid
sequenceDiagram
    participant U as 사용자 (브라우저)
    participant F as FastAPI 백엔드
    participant S as Supabase Auth

    U->>F: API 요청 + Bearer Token
    F->>S: GET /auth/v1/user (토큰 전달)
    S->>F: 200 OK + 유저 정보 (id, email 등)
    F->>U: 디데이 목록 응답
```

### 최종 코드

```python
# app/core/auth.py (최종 버전)
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

def get_current_user(credentials = Depends(HTTPBearer())):
    settings = get_settings()

    # Supabase에 직접 물어보기
    url = f"{settings.supabase_url}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {credentials.credentials}",
        "apikey": settings.supabase_anon_key or "",
    }

    response = httpx.get(url, headers=headers, timeout=10)

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_data = response.json()
    return {"sub": user_data["id"], "email": user_data["email"]}
```

### 왜 이 방식이 더 나은가?

| 비교 항목 | JWT 직접 해독 | Supabase API 호출 |
|:---|:---|:---|
| 필요한 라이브러리 | `PyJWT`, `cryptography`, `ecdsa` | `httpx` (이미 설치됨) |
| 알고리즘 호환성 | HS256/RS256/ES256 각각 대응 필요 | 알고리즘 무관 |
| 환경변수 | `SUPABASE_JWT_SECRET` or Public Key | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` |
| 토큰 만료 처리 | 직접 구현 필요 | Supabase가 자동 처리 |
| Vercel 호환성 | C 바이너리 이슈 발생 | 문제 없음 |
| 속도 | 로컬 검증 (빠름) | 네트워크 요청 (약간 느림) |

> **트레이드오프**: API 호출 방식은 매 요청마다 Supabase 서버에 네트워크 요청을 보내므로 약간의 지연(latency)이 추가됩니다. 하지만 인프트라 복잡도가 현저히 낮아지고, 서버리스 환경과의 호환성이 완벽하므로 현재 프로젝트 규모에서는 최적의 선택입니다.

---

## 5. 교훈 및 요약

### 핵심 교훈

1. **로컬에서 되는 것과 서버리스에서 되는 것은 다르다**
   - C 확장이 필요한 라이브러리(`cryptography`)는 서버리스 환경에서 호환 문제가 발생할 수 있습니다.

2. **Supabase의 JWT 방식은 프로젝트마다 다를 수 있다**
   - 최신 프로젝트: `ES256` (JWT Signing Keys)
   - 레거시 프로젝트: `HS256` (JWT Secret)
   - 대시보드에서 "Legacy JWT secret has been migrated..."가 보이면 ES256입니다.

3. **가장 단순한 해결책이 가장 좋은 해결책이다**
   - 복잡한 암호화 라이브러리 의존성 대신, 이미 제공되는 API를 활용하는 것이 유지보수와 호환성 면에서 훨씬 우수합니다.

### 시도 타임라인

| 시도 | 접근법 | 결과 |
|:---|:---|:---|
| 1 | `HS256` 고정 | ❌ `alg value is not allowed` |
| 2 | `HS256 + RS256 + ES256` 허용 | ❌ `Algorithm not supported` (cryptography 없음) |
| 3 | `requirements.txt`에 cryptography 추가 | ❌ Vercel에서 설치 안 됨 |
| 4 | `PyJWT[crypto]` + 버전 고정 | ❌ 여전히 설치 안 됨 |
| 5 | `pyproject.toml`에도 추가 | ❌ 여전히 설치 안 됨 |
| 6 | JWKS 방식으로 전환 | ❌ 401/404 에러 + cryptography 여전히 필요 |
| 7 | **Supabase API 직접 호출** | ✅ 성공! |

---

## 6. 참고 자료

- [Supabase Auth - Server-side Rendering](https://supabase.com/docs/guides/auth/server-side-rendering)
- [PyJWT Documentation](https://pyjwt.readthedocs.io/)
- [Vercel Python Runtime](https://vercel.com/docs/functions/runtimes/python)
- [JWT.io - JWT 디버거](https://jwt.io/)
