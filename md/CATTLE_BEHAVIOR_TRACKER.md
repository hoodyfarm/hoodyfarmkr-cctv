# 🐄 축사 저해상도(640x360) 실시간 소 행동 상태 추적기 (Cattle Behavior Tracker)

## 📌 1. 개요 및 설계 원리

저해상도 서브 스트림(`640x360`) 환경에서는 단일 프레임만으로 다음 상태들을 구분하기 어렵습니다:
- **정상 휴식 소**: 단순히 배를 깔고 편안히 엎드려 쉼 (흉와, `lying_sternal`)
- **장꼬임 / 고창증 / 산통 소**: 배앓이로 인해 눕다 일어나기를 짧은 주기로 반복함
- **기립불능 / 급성 고창증 소**: 옆으로 완전히 쓰러져 네 다리를 뻗은 채 질식 위험에 처함 (측와, `lying_lateral`)

이를 완벽히 구분하기 위해 **1) 파인튜닝 YOLOv11 클래스** + **2) ByteTrack ID 영속성 유지** + **3) 개체별 시계열 상태 머신(State Machine)**을 결합한 엣지 탐지 아키텍처를 적용합니다.

---

## 🚦 2. 3중 판별 알고리즘 및 경보 등급

| 자세 / 상태 | YOLO 클래스 | 시계열 상태 판정 조건 | 발생 경보 등급 및 액션 |
| :--- | :--- | :--- | :--- |
| **정상 휴식** | `lying_sternal` (1, 흉와) | 30분~2시간 동안 자세 유지, 전환 빈도 낮음 | **NORMAL** (경보 없음) |
| **장꼬임 / 산통 전조** | `standing`(0) ↔ `lying_sternal`(1) | **15분(900초) 윈도우 내 기립↔흉와 전환 4회 이상** 누적 | **`COLIC_SUSPECTED`** (WARNING, 1차 주의/점검 경보) |
| **기립불능 / 급성 고창증** | `lying_lateral` (2, 측와) | **15초 이상 연속 측와 자세 유지** (노이즈 필터링 후 발령) | **`CATTLE_INVERTED`** (CRITICAL, 0.5초 골든타임 긴급 경보) |

### 🛠️ 저해상도(`640x360`) 노이즈 보완 기법
1. **5프레임 다수결 디바운싱 (Majority Voting Debounce)**:
   * 2.5fps 기준 최근 5프레임(약 2초) 동안 과반수(3회 이상) 일치된 자세만 확정 자세(`confirmed_posture`)로 갱신하여 1~2프레임 튐(Jitter) 현상을 차단합니다.
2. **바운딩 박스 종횡비(Aspect Ratio) 보정 휴리스틱**:
   * 모델이 `lying_sternal`로 분류했더라도 Bounding Box 종횡비(`width / height > 2.3`)가 극단적으로 납작한 경우, 측와(`lying_lateral`)로 가중치 보정합니다.
3. **5분 알람 쿨다운 (Alarm Cooldown)**:
   * 동일 개체(`track_id`)에서 동일 경보가 300초(5분) 동안 중복 발송되지 않도록 방지합니다.
4. **1시간 미탐지 트랙 자동 메모리 회수**:
   * 화면 밖으로 퇴장하거나 출하/이동된 소의 상태 객체는 3600초 후 자동 삭제합니다.

---

## ⚙️ 3. 야간 축사 환경 전용 ByteTrack 설정 (`config/cattle_bytetrack.yaml`)

야간 적외선(IR) 환경에서 소가 겹치거나 가려질 때 ID Switch가 일어나 15분 카운트가 리셋되는 현상을 막기 위해 튜닝되었습니다:

```yaml
# config/cattle_bytetrack.yaml
tracker_type: bytetrack
track_high_thresh: 0.45    # 1차 매칭 신뢰도 (야간 IR 화질 고려해 0.5 -> 0.45 하향)
track_low_thresh: 0.15     # 일부 가려진 소도 놓치지 않고 2차 매칭으로 추적 유지
new_track_thresh: 0.55     # 신규 ID 발급 기준을 높여 오탐으로 인한 가짜 ID 생성 억제
track_buffer: 180          # 2.5fps 기준 약 72초 동안 가려져도 기존 ID 영속 유지
match_thresh: 0.85         # 소의 이동 속도가 느리므로 IoU 매칭 허용 범위를 넓게 설정
fuse_score: True
```

---

## 💻 4. 소 행동 상태 추적기 소스 코드 (`src/services/behavior/cattle_behavior_tracker.py`)

* **경로**: `src/services/behavior/cattle_behavior_tracker.py`
* **접근 별칭**: `src/services/cattle_behavior_tracker.py`
* **주요 구성 요소**:
  * `CattleTrackState`: 개체별 raw_history 큐, 확정 자세, 전환 타임스탬프 큐, 쿨다운 추적.
  * `ZoneBehaviorMonitor`: 분할 우방 구역별 ByteTrack 및 다중 개체 상태 수명주기 관리자.

---

## 🔗 5. 기존 후디팜 CCTV 파이프라인 연동 포인트

1. **Stage 1 (0.5초 골든타임 즉각 웹훅)**:
   * `process_frame()` 또는 `process_detections()` 반환 리스트에 `CRITICAL` / `WARNING` 경보가 감지되는 즉시 `event_worker.py`의 `CCTVEventEnvelopeV1` 페이로드로 패키징하여 FMS 웹훅으로 전송.
2. **Stage 2 (15초 MP4 비디오 클립 백그라운드 링버퍼)**:
   * `COLIC_SUSPECTED` 및 `CATTLE_INVERTED` 트리거 시 RAM tmpfs 링버퍼에서 사전 5초 + 사후 10초 = 총 15초 MP4 클립을 생성하여 OCI/G-Drive 저장 후 링크 제공.

---

## 🧪 6. 단위 테스트 검증 결과

* **테스트 파일**: `tests/unit/test_cattle_behavior_tracker.py`
* **테스트 항목**:
  1. `test_debouncing_requires_minimum_frames_and_majority`: 5프레임 미만 미확정 및 과반수 다수결 노이즈 필터링 검증
  2. `test_cattle_inverted_alert_after_15_seconds`: 15초 측와 지속 시 `CATTLE_INVERTED` (CRITICAL) 발생 및 쿨다운 검증
  3. `test_colic_suspected_alert_on_frequent_transitions`: 15분 내 4회 기립↔흉와 반복 시 `COLIC_SUSPECTED` (WARNING) 발생 검증
  4. `test_colic_window_expiration`: 900초 경과된 오래된 전환 타임스탬프 만료 검증
  5. `test_zone_behavior_monitor_aspect_ratio_correction_and_cleanup`: 종횡비 > 2.3 측와 보정 및 3600초 미탐지 트랙 메모리 GC 검증
* **실행 결과**:
  * 신규 단위 테스트: **5 / 5 통과 (100% PASSED)**
  * 전체 프로젝트 회귀 테스트: **74 / 74 통과 (100% PASSED)**
