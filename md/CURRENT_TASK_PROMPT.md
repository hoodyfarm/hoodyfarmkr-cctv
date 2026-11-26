# 📋 후디팜 CCTV AI Vision 작업 관리 및 프롬프트 명세서 (CURRENT_TASK_PROMPT.md)

본 문서는 **hoodyfarmkr-cctv** 프로젝트의 고도화 작업 순서를 정의하고, 차례대로 실행할 수 있도록 작업별 프롬프트 명세를 관리하는 문서입니다.
작업 상태는 **[완결]**, **[진행중]**, **[예정]** 3단계로 추적됩니다.

---

## 🚦 전체 작업 현황 대시보드 (Status Summary)

| 순번 | 작업 코드 | 작업명 | 상태 | 주요 대상 모듈 |
| :---: | :---: | :--- | :---: | :--- |
| **0** | `TASK-CLIP-10S` | **10초 클립 생성 버퍼 설정 및 단위 테스트 검증** | **[완결]** | `hoodyfarm.yaml`, `config.py` |
| **1** | `TASK-CATTLE-BEHAVIOR` | **소 이상행동(산통/기립불능) 시계열 상태 추적기 및 ByteTrack 튜닝** | **[완결]** | `cattle_behavior_tracker.py`, `cattle_bytetrack.yaml` |
| **2** | `TASK-CCTV-NET-RESERVE` | **축사 CCTV 10대 네트워크 스캔 및 공유기 DHCP 주소 예약 표준화** | **[완결]** | `hoodyfarm.yaml`, `.env`, `CCTV_NETWORK_RESERVATION.md` |
| **3** | `TASK-LOCAL-FILTER` | **3500X 1차 필터 고도화: 장폐색(산통)·기립불능 실시간 엣지 파이프라인 결합** | **[완결]** | `inference_worker.py` |
| **4** | `TASK-DATASET-PIPELINE` | **축사 10대 CCTV 프레임 자동 수집기 및 반자동 의사 라벨러·학습 파이프라인** | **[완결]** | `dataset_collector.py`, `auto_labeler.py`, `train_yolo.py` |
| **5** | `TASK-E2E-PIPE` | **3500X ➔ FMS 10초 클립 웹훅 송수신 E2E 실측 검증** | **[진행중]** | `event_worker.py`, `fms_client.py` |
| **6** | `TASK-WATER-ROI` | **음수조(물통) ROI 체류 시간 추적 및 음수 거부 감지기** | **[예정]** | `src/services/behavior/` |
| **7** | `TASK-NIGHT-SLEEP` | **야간 수면 및 기립/횡와(진통/불안정) 시계열 로거** | **[예정]** | `src/services/behavior/` |
| **8** | `TASK-GEMINI-PLUGIN` | **Gemini 2.5 Flash 정밀 행동/외형 판독 프롬프트 연동** | **[예정]** | `gemini_service.py` |
| **9** | `TASK-AUDIO-COUGH` | **CCTV RTSP 오디오 기반 호흡기 기침 음향 감지기** | **[예정]** | `src/services/audio/` |

---

## 📝 상세 작업별 프롬프트 명세 (Prompt Specifications)

---

### [완결] TASK-CLIP-10S: 10초 클립 생성 버퍼 설정 및 단위 테스트 검증
* **상태**: **[완결]** (2026-11-21 완료)
* **목표**: 사건 발생 전 5초 + 후 5초 = 총 10초 MP4 클립 생성을 위한 파라미터 조정
* **반영 내역**:
  * `config/farms/hoodyfarm.yaml`: `ring_buffer_sec: 20.0`, `pre_event_sec: 5.0`, `post_event_sec: 5.0`
  * `src/config.py`: `CLIP_PRE_EVENT_SEC: 5.0`, `CLIP_POST_EVENT_SEC: 5.0`
  * 단위 테스트 `tests/unit/test_p1_ports_and_profile.py` 100% 통과 확인.

---

### [완결] TASK-CATTLE-BEHAVIOR: 소 이상행동(산통/기립불능) 시계열 상태 추적기 및 ByteTrack 튜닝
* **상태**: **[완결]** (2026-11-22 완료)
* **목표**: 저해상도(640x360) 서브스트림 환경에서 단순 휴식 소, 산통(장꼬임/고창증) 소, 기립불능(측와) 소를 시계열 상태 머신으로 판별
* **반영 내역**:
  * `config/cattle_bytetrack.yaml`: 야간 IR 및 가림 대응 파라미터 (track_buffer 180, track_high_thresh 0.45 등)
  * `src/services/behavior/cattle_behavior_tracker.py`: 다수결 디바운싱(5프레임), 종횡비(>2.3) 보정, 15초 측와 기립불능(`CATTLE_INVERTED`), 15분 내 4회 이상 기립↔횡와 반복 산통(`COLIC_SUSPECTED`) 판정기
  * 단위 테스트 `tests/unit/test_cattle_behavior_tracker.py`: 5개 시나리오 100% 통과 (전체 회귀 84건 통과)
  * 기술 문서: `md/CATTLE_BEHAVIOR_TRACKER.md` 생성 완료

---

### [완결] TASK-CCTV-NET-RESERVE: 축사 CCTV 10대 네트워크 스캔 및 공유기 DHCP 주소 예약 표준화
* **상태**: **[완결]** (2026-11-22 완료)
* **목표**: TP-Link Archer AX73 기반 CCTV 10대의 MAC 주소 스캔 및 CCTV 9대(201, 12~19) 및 NVR(2) 고정 예약 표준화
* **반영 내역**:
  * 축사 LAN 서브넷 스캔으로 10대 CCTV RTSP 포트 및 MAC 주소 전수 추출
  * `config/farms/hoodyfarm.yaml`: `192.168.0.201` (CAM01), `192.168.0.12` (CAM02) 외 9대 전수 기본값 갱신
  * `.env`, `.env.example`: 주소 예약 고정 IP 및 MAC 주소 참조 정보 동기화
  * 기술 문서: `md/CCTV_NETWORK_RESERVATION.md` 작성 완료

---

### [진행중] TASK-E2E-PIPE: 3500X ➔ FMS 10초 클립 웹훅 송수신 E2E 실측 검증
* **상태**: **[진행중]**
* **목표**: 3500X 로컬 엣지에서 생성된 10초 MP4 클립과 대표 스냅샷이 FMS 웹훅 엔드포인트(`POST /api/v1/cctv-events`)로 정상 전달되고, FMS 화면에서 재생 가능한지 배관(1 ➔ 3) 무결성 검증.
* **실행 프롬프트**:
  ```markdown
  # Directive: 3500X ➔ FMS 10초 클립 웹훅 전송 및 재생 E2E 검증
  1. 3500X의 `POST /api/v1/pipeline/trigger` 수동 엔드포인트를 호출하여 10초 클립 생성 트리거를 발생시킵니다.
  2. `captures/clips/` 디렉터리에 10초 길이의 MP4 클립이 생성되는지 파일 크기와 재생 길이를 확인합니다.
  3. FMS Webhook(`FMS_WEBHOOK_URL`)으로 전송되는 CCTVEventEnvelopeV1 페이로드의 `media_urls.tailscale_clip_url` 및 `drive_clip_url`이 유효한지 확인합니다.
  4. FMS 웹 UI 또는 로컬 수신 로그에서 10초 영상이 정상적으로 스트리밍/재생되는지 확인합니다.
  ```

---

### [완결] TASK-LOCAL-FILTER: 3500X 1차 필터 고도화: 장폐색(산통)·기립불능 실시간 엣지 파이프라인 결합
* **상태**: **[완결]** (2026-11-23 완료)
* **목표**: `ZoneBehaviorMonitor`를 `InferenceWorker`의 `process_frame` 루프에 결합하여 장폐색/산통 전조(`COLIC_SUSPECTED`) 및 기립불능(`CATTLE_INVERTED`) 시 즉각 이벤트 승격 및 10초 MP4 클립/웹훅 전송 파이프라인 가동.
* **반영 내역**:
  * `src/services/inference_worker.py`: `ZoneBehaviorMonitor` 연동, BBox Aspect Ratio 분석 기반 `CLASS_LYING_LATERAL` 보정, 이상행동 감지 시 최우선 이벤트 라벨 승격 및 알람 전송.
  * 단위 테스트 `tests/unit/test_inference_behavior_integration.py` 100% All-Green 통과.

---

### [완결] TASK-DATASET-PIPELINE: 축사 10대 CCTV 프레임 자동 수집기 및 반자동 의사 라벨러·학습 파이프라인
* **상태**: **[완결]** (2026-11-23 완료)
* **목표**: 라벨링 데이터 부재 문제를 해결하기 위해 축사 10대 CCTV로부터 주/야간 프레임 자동 수집, 4대 행동 클래스 반자동 의사 라벨링, YOLO11n 파인튜닝 학습 자동화 파이프라인 구축.
* **반영 내역**:
  * `src/tools/dataset_collector.py`: 축사 10대 CCTV 순회 프레임 자동 수집 (조도/시간대 카테고리 태깅).
  * `src/tools/auto_labeler.py`: 4개 행동 클래스(`standing`, `lying_sternal`, `lying_lateral`, `mounting`) 기하학적 형태 기반 YOLO 포맷 TXT 자동 생성 및 5초 검수용 프리뷰 이미지 생성.
  * `src/tools/train_yolo.py`: Train/Val 8:2 자동 분할, `cattle_behavior.yaml` 생성 및 YOLO11n 파인튜닝 실행기.
  * 단위 테스트 `tests/unit/test_dataset_and_training_tools.py` 100% 통과.

---

### [예정] TASK-WATER-ROI: 음수조(물통) ROI 체류 시간 추적 및 음수 거부 감지기
* **상태**: **[예정]**
* **목표**: 물통 가상 ROI를 설정하고 소 머리의 체류 시간/접근 빈도를 누적하여 탈수 및 질병 전조 증상 감지.
* **실행 프롬프트**:
  ```markdown
  # Directive: 음수조 가상 구역(ROI) 체류 시간 분석 모듈 구현
  1. `hoodyfarm.yaml`에 물통 관심 구역 좌표(`water_trough_roi: [[x1, y1], [x2, y2]]`) 설정 스키마를 추가합니다.
  2. IngestionWorker/InferenceWorker에서 소의 머리(Head) 중심점이 해당 ROI 내에 진입한 체류 시간(초)과 일일 접근 횟수를 카운트하는 서비스를 작성합니다.
  3. 설정된 시간(예: 12시간) 동안 음수 접근이 없거나 평소 대비 급감 시 `EVENT_TYPE='DEHYDRATION_RISK'` 이벤트를 발행하도록 연결합니다.
  ```

---

### [예정] TASK-NIGHT-SLEEP: 야간 수면 및 기립/횡와(진통/불안정) 시계열 로거
* **상태**: **[예정]**
* **목표**: 야간(22:00 ~ 05:00) 소의 횡와(휴식) 및 기립 반복 횟수를 시계열로 기록하여 수면 장애, 분만 진통, 환경 불량 자동 탐지.
* **실행 프롬프트**:
  ```markdown
  # Directive: 야간 가축 수면 및 자세 전환(Restlessness) 로거 구현
  1. 야간 시간대를 판별하여 1분 주기로 우방 내 소의 기립/횡와 상태를 로깅하는 백그라운드 태스크를 작성합니다.
  2. 잦은 기립-착석 반복(진통/복통 패턴) 또는 장시간 기립(수면 불가 패턴) 발생 시 수면 불안정 지수(Restlessness Index)를 계산합니다.
  3. 지수가 임계치를 초과하면 `EVENT_TYPE='RESTLESSNESS_ALERT'` 웹훅을 발송합니다.
  ```

---

### [예정] TASK-GEMINI-PLUGIN: Gemini 2.5 Flash 정밀 행동/외형 판독 프롬프트 연동
* **상태**: **[예정]**
* **목표**: 3500X가 선별한 스틸컷 1장을 실제 유효한 Gemini 2.5 Flash API로 전송하여 수의학적 상태 진단(기립불능, 분만, 통증)을 고도화.
* **실행 프롬프트**:
  ```markdown
  # Directive: Gemini 2.5 Flash 멀티모달 프롬프트 정밀 튜닝 및 실서버 연동
  1. `.env`에 유효한 `GEMINI_API_KEY`를 주입하고 `src/services/gemini_service.py`의 구조화된 출력 스키마를 점검합니다.
  2. 프롬프트에 가축 고통 지수(Grimace Scale), 귀 처짐, 꼬리 치켜듦(분만), 복부 팽창 여부를 판독할 수 있도록 수의학적 행동 지침을 추가합니다.
  3. 1차 로컬 필터에서 전달된 의심 프레임 1장에 대해 Gemini가 정확한 판정 JSON과 한국어 요약을 반환하는지 검증합니다.
  ```

---

### [예정] TASK-AUDIO-COUGH: CCTV RTSP 오디오 기반 호흡기 기침 음향 감지기
* **상태**: **[예정]**
* **목표**: CCTV 내장 마이크의 오디오 스트림을 수신하여 호흡기 기침 소리를 감지하고 폐렴 조기 경보 발령.
* **실행 프롬프트**:
  ```markdown
  # Directive: RTSP 오디오 스트림 수신 및 기침 음향 감지 엔진 구축
  1. CCTV RTSP URL에서 오디오 스트림을 디코딩하는 경량 수집 모듈을 작성합니다.
  2. 소 기침 소리의 음향 주파수 특성(파열음 대역)을 필터링하거나 초경량 음향 분류기(YAMNet)를 연결합니다.
  3. 단위 시간 내 기침 빈도가 초과될 때 `EVENT_TYPE='COUGH_DETECTED'` 이벤트를 생성하여 FMS로 알림을 보냅니다.
  ```
