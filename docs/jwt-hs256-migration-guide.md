# JWT HS256 직접 검증 전환 가이드

> 현재는 Supabase API 호출 방식으로 인증을 처리하고 있습니다.  
> 나중에 트래픽이 늘거나 성능 최적화가 필요할 때, 이 문서를 보고 HS256 직접 검증 방식으로 전환하세요.

---

## 현재 방식 vs 전환 후 방식

| 항목 | 현재 (Supabase API 호출) | 전환 후 (HS256 직접 검증) |
|:---|:---|:---|
| 검증 속도 | ~50-200ms (네트워크) | ~0.1ms (로컬 계산) |
| 외부 의존성 | Supabase 서버 필수 | 없음 (독립적) |
| 필요 라이브러리 | `httpx` | `PyJWT` (이미 설치됨) |
| 필요 환경변수 | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | `SUPABASE_JWT_SECRET` |
| Supabase 장애 시 | 우리 서비스도 인증 불가 | 정상 동작 |

---

## 전환 시점 기준

아래 중 하나라도 해당되면 전환을 고려하세요:

- [ ] Supabase 무료 플랜 API 호출 한도에 근접할 때
- [ ] 동시 접속자가 100명 이상으로 늘어날 때
- [ ] 인증 응답 속도가 체감될 정도로 느려질 때
- [ ] Docker 기반 배포(AWS, GCP 등)로 이전할 때

---

## 전환 절차

### 1단계: Supabase에서 JWT Secret 복사

1. [Supabase Dashboard](https://app.supabase.com/) > Project Settings > API
2. **JWT Settings** 섹션 > **Legacy JWT Secret** 탭
3. `JWT Secret` 값 복사 (이미 활성화해 두었으므로 바로 사용 가능)

### 2단계: Vercel 환경변수 추가

- Vercel Settings > Environment Variables
- `SUPABASE_JWT_SECRET` 추가 → 복사한 값 붙여넣기

### 3단계: `app/core/auth.py` 교체

아래 코드로 파일 전체를 교체합니다:

```python
"""Authentication – verify Supabase JWT locally (HS256)."""

from __future__ import annotations

import logging
from typing import Mapping, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

logger = logging.getLogger(__name__)
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Mapping[str, Any]:
    """Verify the Supabase JWT token locally using HS256."""
    settings = get_settings()

    if not settings.supabase_jwt_secret:
        logger.warning("SUPABASE_JWT_SECRET not configured. Using dummy user.")
        return {"sub": "developer-user-123", "email": "dev@example.com"}

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
```

### 4단계: 배포 및 테스트

```bash
git add app/core/auth.py
git commit -m "feat: switch to HS256 local JWT verification"
git push origin main
```

Vercel Redeploy 후 로그인 → 디데이 목록 확인

---

## 주의사항

> [!CAUTION]
> Supabase 대시보드에서 Legacy JWT Secret을 **Rotate(변경)** 하면, 기존에 발급된 모든 토큰이 무효화됩니다. 변경 시 모든 사용자가 재로그인해야 합니다.

> [!IMPORTANT]
> HS256은 `cryptography` 라이브러리가 필요 없습니다. 순수 파이썬(`PyJWT`)만으로 동작하므로 Vercel 서버리스 환경에서도 문제없습니다.
