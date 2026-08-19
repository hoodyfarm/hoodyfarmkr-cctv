# 🤖 Gemini 2.5 Flash 기반 CCTV 파이프라인 Python 리팩토링 프롬프트

> **문서 위치**: `md/REFACTORING_PROMPT.md`  
> **타겟 모델**: Gemini 2.5 Flash (`google-genai` SDK)  
> **작업 목표**: 절차적/동기식 Python 및 OpenCV/CCTV 처리 코드를 비동기 FastAPI, Pydantic v2 Structured Output, SQLAlchemy 2.0 (Async) 3-Tier 모듈로 변환  
> **산출물**: 타입 안전한 Python 모듈 + Pytest 단위 테스트 코드  

---

## 🎯 AI 프롬프트 본문 템플릿

```markdown
# Task: [FastAPI & Async Refactoring] CCTV AI 파이프라인 모듈화 및 TDD 구축

당신은 Python 3.11+, FastAPI, OpenCV, SQLAlchemy 2.0 (asyncio), Gemini 2.5 Flash SDK에 정통한 수석 백엔드 아키텍트입니다.
제시된 코드/모듈을 읽고 아래의 **Golden Rules**를 엄격히 준수하여 리팩토링 및 모듈 분리를 수행해주세요.

### 📌 5대 리팩토링 준수 규칙 (Golden Rules)

1. **Async-First & Non-Blocking**:
   - I/O 작업 (DB, OCI, Gemini API, Network Stream)은 반드시 `async / await` 비동기 함수로 구현합니다.
   - OpenCV 프레임 캡처 등 동기식 CPU/C-extension 작업은 `asyncio.to_thread`를 활용하여 메인 이벤트 루프 블로킹을 방지합니다.

2. **Pydantic v2 & Structured Output Validation**:
   - API 요청/응답 및 AI 분석 결과는 엄격한 Pydantic `BaseModel` 스키마로 검증합니다.
   - Gemini API 호출 시 `response_mime_type="application/json"`과 `response_schema`를 지정하여 타입 안전성을 보장합니다.

3. **Fail-Safe & Circuit Breaker**:
   - RTSP 끊김, AI API 한도 초과, DB 연결 장애 시 자동 재시도(Retry with Backoff) 및 예외 복구(Fallback) 메커니즘을 포함합니다.

4. **Layered 3-Tier Architecture**:
   - `src/api/` (FastAPI Router)
   - `src/services/` (비즈니스 로직 & AI/Stream 엔진)
   - `src/db/` & `src/schemas/` (ORM 모델 & 데이터 구조)

5. **TDD (Pytest) 동시 제공**:
   - 리팩토링된 모듈과 함께 100% 검증 가능한 `pytest` 단위 테스트 (`tests/unit/test_*.py`) 모듈을 함께 작성합니다.

---

### 📝 대상 코드 (Target Code):
[여기에 리팩토링할 기존 코드 입력]
```
