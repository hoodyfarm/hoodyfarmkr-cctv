# 🎯 CCTV REPO TASK PROMPT: AI 정밀 진단 의뢰 & FMS 관제 연동 2대 파이프라인 구축

> **문서 용도**: `hoodyfarmkr-cctv` 레포지토리 전용 2대 핵심 연동 파이프라인 실행 명세  
> **발행 일시**: 2026-11-28 16:15 KST  
> **참조 명세**: [`config/farms/hoodyfarm.yaml`](file:///d:/workspace/hoodyfarmkr-cctv/config/farms/hoodyfarm.yaml), [`src/domain/events/event_envelope.py`](file:///d:/workspace/hoodyfarmkr-cctv/src/domain/events/event_envelope.py)  
> **목표 브랜치**: `feat/cctv-ai-diagnosis-and-fms-webhook-pipeline` ➔ `main` & `dev`

---

## 📱 착수 전 필드 체감 3줄 프리뷰
1. **[현장 조작]**: 축사 카메라(1~9번사)에서 소가 15초 이상 옆으로 눕거나(기립불능) 산통 징후(반복 눕기/서기)가 발생하면 엣지 YOLO가 이를 감지하여 6초 비디오 클립과 고화질 스냅샷을 자동 추출한다.
2. **[화면/시트 변화]**: 캡처된 미디어가 OCI 버킷 및 Google Drive에 동시 보관되며, Gemini 2.5 Flash가 수 초 내에 *"3번사 한우 기립불능 의심(긴급도: CRITICAL)"* 한국어 소견을 생성하여 FMS 대시보드와 모바일 푸시 알림으로 즉각 팝업된다.
3. **[예외 방어]**: 현장 농가 인터넷 순단이나 FMS 서버 점검 중에도 이벤트가 1건도 유실되지 않도록 로컬 SQLite `WebhookOutbox` 큐에 안전 격리되고, 망 복구 시 100% 자동 재전송(DLQ)된다.

---

## 📊 순차 릴레이 큐 (Pre-Baked Sequential Queue)

### [태스크 1/2] AI 정밀 진단 의뢰 파이프라인 (`InferenceWorker` ➔ `Storage` ➔ `GeminiVisionService`)
- **[목표]**: YOLO11n 1차 감지된 이상 징후 프레임/클립을 OCI/Google Drive에 적재하고 Gemini 2.5 Flash 멀티모달 API를 통해 정형 진단 리포트를 생성하는 자동 의뢰 파이프라인 완성
- **[타겟]**: `src/services/inference_worker.py`, `src/services/gemini_service.py`, `src/pipeline/event_worker.py`
- **[지시]**:
  1. 이상행동 감지 시 스냅샷 프레임 및 링 버퍼 기반 6초 MP4 클립 인코딩 연동
  2. `OCIDataPipelineService` 및 `GoogleIntegrationService`를 통한 2-Tier 미디어 업로드 및 서명 URL(Signed URL) 확보
  3. `GeminiVisionService.analyze_frame_structured()` 호출로 한국어 AI 종합 진단 소견 및 심각도(CRITICAL/WARNING) 정형 데이터 바인딩
- **[검증]**: `pytest tests/unit/test_gemini_structured_unit.py tests/unit/test_signed_url_pipeline.py` 통과

### [태스크 2/2] FMS 관제 시스템 연동 파이프라인 (`EventWorker` ➔ `EventEnvelopeV1` ➔ `WebhookOutbox` ➔ `FMS Webhook`)
- **[목표]**: 진단 결과와 2단 미디어 링크를 `EventEnvelopeV1` 표준 스키마로 패키징하여 FMS 실서버(`FMS_WEBHOOK_URL`)로 실시간 발송하고, 장애 시 Outbox DLQ로 무손실 보존
- **[타겟]**: `src/infrastructure/webhook/fms_client.py`, `src/infrastructure/webhook/outbox.py`, `src/domain/events/event_envelope.py`
- **[지시]**:
  1. `CCTVEventEnvelopeV1` 내 `schema_version`, `farm_id`, `camera_id`, `event_code`, `media_urls`, `ai_summary` 완전 바인딩
  2. `FMSWebhookClient.notify()` 발송 실패 시 로컬 SQLite `WebhookOutbox`로 0초 격리 적재
  3. 백그라운드 재시도 워커(`outbox.process_due()`) 지수 백오프 자동 발송 루프 점검
- **[검증]**: `src/tools/test_e2e_integration.py` 5단계 ALL-PASS 및 `npm run da` 3대 세이프가드 통과
