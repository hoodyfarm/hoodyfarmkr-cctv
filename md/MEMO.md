# 📌 hoodyfarmkr-cctv 단기 작업 메모 (MEMO)

## Part 1. 핵심 메모 (Core Memos)
* **[WIP: 2026-08-19 13:06]** - 진행상황: [6단계 완료] FMS AI 자동화 체계 CCTV 이식 완료 (Gemini 2.5 Flash 기반 AICodeRefinerService, CLI 진단도구 test_code_refiner.py, REFACTORING_PROMPT.md, TICKTOCK.md, workflow-start/end 고도화) -> 다음에 할 일: 로컬 파이썬 가상환경(.venv) 생성/연결 후 npm run refine 및 전체 자가진단 실행
* **[WIP: 2026-08-12 13:58]** - 진행상황: [5단계 전체 완료] PipelineOrchestrator 파이프라인 수집-분석-저장-OCI업로드-알림 루프 통합, Dockerfile & docker-compose.yml (App+PostgreSQL) 생성, src/tools/test_orchestrator.py CLI 진단 도구 및 README.md 가이드 작성 완료 -> 다음 할 일: feat/env 브랜치 테스트 및 OCI 배포
* **[WIP: 2026-08-12 13:56]** - 진행상황: [4단계 완료] Gemini 2.5 Flash (`google-genai` SDK) 멀티모달 API 연동, Pydantic Structured Output 스키마(CCTVAnalysisResultSchema, DetectedObject), src/tools/test_gemini.py CLI 진단 도구 구현 -> 다음 할 일: [5단계] 파이프라인 오케스트레이터 및 Docker/OCI 배포 구성
* **[WIP: 2026-08-12 13:55]** - 진행상황: [3단계 완료] PostgreSQL asyncpg + SQLAlchemy 2.0 ORM 모델(CCTVDevice, FrameLog, AIAnalysisResult, AlertEvent) 및 src/tools/test_db.py CLI 진단 도구 작성 -> 다음 할 일: [4단계] Gemini 2.5 Flash API 연동 및 Structured Output 모듈 구축
* **[WIP: 2026-08-12 13:53]** - 진행상황: [2단계 완료] ONVIF/RTSP Dual-Fallback 주소 extraction, OpenCV 자동 재연결(Auto-Reconnect) 캡처, 모션 델타 계산, Synthetic Test Frame 생성기, src/tools/test_stream.py CLI 진단 도구 구현 -> 다음 할 일: [3단계] PostgreSQL DB 스키마 및 asyncpg/SQLAlchemy 2.0 연동 모듈 구축
* **[WIP: 2026-08-12 13:46]** - 진행상황: [1단계 완료] ONVIF/RTSP, PostgreSQL, OCI, Gemini 2.5 Flash 최상위 .env 및 src/config.py 구성, scripts/branch.js 생성 -> 다음 할 일: [2단계] RTSP 프레임 수집 및 ONVIF 영상 테스트 모듈 작성
* **[WIP: 2026-08-10 12:51]** - 진행상황: 신규 CCTV레포지토리 개설 feat: refactor into TDD architecture with pytest fixtures, unit/integration split, and coverage scripts -> 내일 할 일: 기본 뼈대 재점검
* **[WIP: 2026-08-10 12:45]** hoodyfarmkr-cctv 초기 레포지토리 구축 완료 (ONVIF + OCI + Gemini AI 구조 파이프라인)

## Part 2. 주요 환경 정보
- Python 가상환경: `.venv`
- 서버 실행 명령어: `uvicorn src.main:app --reload --port 8000`
- 자가진단 실행: `python src/tools/check_env.py`
