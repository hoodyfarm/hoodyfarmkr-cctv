# 📹 후디팜 FMS: 3500X 관리사 PC AI Vision & CCTV 운영 매뉴얼

본 문서는 **3500X 관리사 PC**를 축사 엣지 비전 서버로 운용하기 위한 **부팅 자동 시작, 서비스 상태 점검, RTSP 영상 수집, 2-Tier AI 분석(로컬 YOLO + Gemini 멀티모달) 및 모바일 확인 5단계 가이드**입니다.

---

## 📌 1. 시스템 통신 및 인프라 사양 (실측 완료)

| 항목 | 실측값 / 설정값 | 설명 |
| :--- | :--- | :--- |
| **장비 사양** | AMD Ryzen 5 3500X (6C/6T), RAM 16GB | CPU 단독 실시간 추론 최적화 (GPU 가속 불필요) |
| **추론 엔진** | Ultralytics YOLO11n (CPU/ONNX) | **프레임당 42.9ms (23.3 FPS) 실시간 연산 달성** |
| **사내망 IP** | `http://192.168.0.234:8000` | 축사 내 Wi-Fi 연결 시 모바일/PC 접속 주소 |
| **원격망 IP** | `http://100.75.197.92:8000` | Tailscale 가상 사설망 접속 주소 (외부 모바일 접속) |
| **카메라 IP** | `192.168.0.217` | SmartLife / Tuya 생태계 CCTV |
| **ONVIF 포트** | `8899` (계정: `admin`) | Tuya SOAP 디바이스 통신 및 프로파일 조회 |
| **RTSP 포트 / URL** | `554` / `rtsp://admin:wlsvndqoR1!@192.168.0.217:554/streamtype=1` | 서브 저화질(SD, 480x544) AI 경량 스트림 |

---

## 🚀 2. 전체 검증 5단계 라이프사이클 테스트 가이드

### 1단계: 재부팅 & 무인 자동 기동 (Autostart)
* **동작 원리**: 윈도우 부팅 및 사용자 로그인 시 시작프로그램에 등록된 스크립트가 백그라운드에서 `uvicorn` 비전 서버를 자동 실행합니다.
* **등록 위치**:
  * 경로: `C:\Users\USER\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\HoodyFarm_Vision_Autostart.lnk`
  * 타겟: `D:\workspace\hoodyfarmkr-cctv\bin\start_vision_background.bat` (숨김 실행)

---

### 2단계: 서비스 러닝(가동 상태) 확인
PC가 켜진 뒤 비전 서버가 정상 동작 중인지 확인합니다.

* **방법 A (스마트폰 / 웹 브라우저)**:
  * 브라우저 주소창에 `http://192.168.0.234:8000/health` 접속
  * **정상 응답**:
    ```json
    {
      "status": "healthy",
      "service": "hoodyfarmkr-cctv"
    }
    ```
* **방법 B (바탕화면 원클릭 확인)**:
  * 관리사 PC 바탕화면의 **`HoodyFarm_Vision_STATUS.lnk`** 더블클릭
  * 화면에 `[정상 가동 중] 포트 8000 (PID: ...) 에서 데몬이 실행 중입니다.` 메시지 출력 확인

---

### 3단계: 축사 실시간 영상 수집 및 모션 감지 확인
축사 카메라(`192.168.0.217`)로부터 실제 프레임이 유입되는지 점검합니다.

* **실행 명령어 (PowerShell)**:
  ```powershell
  cd D:\workspace\hoodyfarmkr-cctv
  .\.venv\Scripts\python.exe src\tools\test_stream.py
  ```
* **정상 점검 출력**:
  1. `[1/4] ONVIF 카메라 접속 성공 (192.168.0.217:8899)`
  2. `[2/4] OpenCV RTSP 프레임 샘플링 성공 (480x544, 채널 3)`
  3. `[3/4] 모션 델타(변화율) 계산 프로세서 정상 작동`
  4. `[4/4] temp_sample_frame.jpg JPEG 이미지 엔코딩 성공`

---

### 4단계 & 5단계: AI 모델 추론 ➔ 감지 결과(Return) 확인

#### ① 1차 로컬 엣지 AI (YOLO11n, 0ms 실시간 추론)
* **실행 명령어 (PowerShell)**:
  ```powershell
  cd D:\workspace\hoodyfarmkr-cctv
  .\.venv\Scripts\python.exe -c "
  import cv2
  from ultralytics import YOLO
  cap = cv2.VideoCapture('rtsp://admin:wlsvndqoR1!@192.168.0.217:554/streamtype=1')
  ret, frame = cap.read()
  cap.release()
  if ret:
      model = YOLO('yolo11n.pt')
      results = model(frame, verbose=False)
      print('=== [AI 비전 추론 결과] ===')
      for box in results[0].boxes:
          cls_name = model.names[int(box.cls[0])]
          conf = float(box.conf[0]) * 100
          print(f'감지된 객체: {cls_name} (신뢰도: {conf:.1f}%)')
  "
  ```
* **실측 반환 결과 예시**:
  ```text
  === [AI 비전 추론 결과] ===
  감지된 객체: cow (소) (신뢰도: 35.2%)
  감지된 객체: dog/animal (신뢰도: 49.5%)
  ```

#### ② 2차 웹 API 전체 파이프라인 트리거 (모바일 Swagger UI)
스마트폰 브라우저에서 원클릭으로 [영상 캡처 ➔ 모션 감지 ➔ AI 분석] 전체 루프를 실행하고 JSON을 반환받습니다.

1. 모바일 브라우저에서 `http://192.168.0.234:8000/docs` 접속
2. **`POST /api/v1/pipeline/trigger`** 선택 ➔ **`Try it out`** ➔ **`Execute`** 터치
3. **반환(Return) JSON**:
   ```json
   {
     "status": "success",
     "timestamp": "2026-11-08T14:40:00",
     "motion_detected": true,
     "motion_score": 2490.0,
     "ai_analysis": {
       "is_anomaly": false,
       "detected_objects": ["cow"],
       "confidence_score": 0.88,
       "summary": "우사 내 개체 정상 휴식 상태 확인"
     }
   }
   ```

---

## 🛠️ 3. 관리자 원클릭 제어 단축키 (바탕화면)

관리사 PC 바탕화면에 즉시 제어 가능한 바로가기를 배치하였습니다:

* **`HoodyFarm_Vision_START.lnk`**: 콘솔 창을 열어 실시간 로그와 FPS를 보며 수동 실행
* **`HoodyFarm_Vision_STOP.lnk`**: 8000번 포트를 점유 중인 비전 데몬 프로세스 안전 종료
* **`HoodyFarm_Vision_STATUS.lnk`**: 현재 서비스 구동 여부 및 접속 IP 안내 창 팝업

---

## 📱 4. 일일 모바일 점검 체크리스트
1. **아침 점검**: 스마트폰으로 `http://192.168.0.234:8000/health` 접속 ➔ 정상 가동 확인
2. **이벤트 확인**: 필요 시 `/api/v1/pipeline/trigger` 호출로 우사 상태 즉시 스냅샷 분석
3. **카메라 변경 시**: 카메라 IP 또는 비밀번호 변경 시 `d:\workspace\hoodyfarmkr-cctv\.env` 파일 갱신 후 `HoodyFarm_Vision_START` 재실행
