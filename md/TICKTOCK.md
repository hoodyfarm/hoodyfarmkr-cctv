# ⏱️ hoodyfarmkr-cctv 틱톡(Tick-Tock) 개발 전선 단권화 전략

> **문서 위치**: `md/TICKTOCK.md`  
> **최종 현행화 날짜:** 2026-08-19  
> **핵심 개념:** 실시간 CCTV 비전 AI 개발과 OCI Cloud/Async DB 인프라 고도화 시 발생하는 피로도를 차단하기 위한 **틱톡(Tick-Tock) 페이징 전략** 문서입니다.

---

## 🧭 틱톡(Tick-Tock) 운영 아키텍처

```
[ 🟢 Tick 페이즈: 신규 비전 AI & 스트림 기능 개발 ]
 ├── ONVIF/RTSP 프레임 수집 모듈 고도화
 ├── OpenCV 모션 계산 & Gemini 2.5 Flash 멀티모달 객체/이상 감지 기능 개발
 └── 독립 자가진단 CLI (`src/tools/test_stream.py`, `test_gemini.py`)로 기능 집중 검증

[ 🔵 Tock 페이즈: 인프라 고도화 & 리팩토링 & Self-Healing ]
 ├── PostgreSQL Asyncpg 연결 풀 최적화 & OCI Object Storage 백그라운드 업로드 튜닝
 ├── Docker Container / GPU-CPU 리소스 빌드 최적화
 └── `src/services/ai_code_refiner.py`를 활용한 런타임 에러 자동 복구 & Pytest TDD 강화
```

---

## 📌 단권화 메모 (SSOT) 파일 매핑

- **단기 작업 맥락**: [`md/MEMO.md`](file:///d:/workspace/hoodyfarmkr-cctv/md/MEMO.md)
- **장기 작업 히스토리**: [`md/docs/HISTORY.md`](file:///d:/workspace/hoodyfarmkr-cctv/md/docs/HISTORY.md)
- **전체 구축 계획서**: [`md/ONVIF_OCI_SETUP_PLAN.md`](file:///d:/workspace/hoodyfarmkr-cctv/md/ONVIF_OCI_SETUP_PLAN.md)
- **AI 리팩토링 프롬프트**: [`md/REFACTORING_PROMPT.md`](file:///d:/workspace/hoodyfarmkr-cctv/md/REFACTORING_PROMPT.md)
