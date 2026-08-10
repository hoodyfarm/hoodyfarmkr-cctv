# hoodyfarmkr-cctv

SmartLife CCTV (ONVIF/RTSP) 영상 수집, Oracle Cloud Infrastructure (OCI) 영상 저장 및 정제, Gemini AI 멀티모달 파이프라인 연동 서비스

## 주요 기능

1. **SmartLife CCTV (ONVIF/RTSP) 수집**
   - ONVIF 프로토콜 디스커버리 및 RTSP 스트림 엔드포인트 연동
   - 실시간 MJPEG 웹 스트리밍 및 키프레임/모션 샘플링
2. **Oracle Cloud Infrastructure (OCI) 데이터 파이프라인**
   - OCI Object Storage 버킷에 원본 비디오 및 정제 프레임 자동 업로드
   - 영상 메타데이터 (타임스탬프, 카메라 ID, 모션 유무) 구조화 및 로깅
3. **Gemini AI 데이터세트 정제 및 파이프라인**
   - 정제된 키프레임을 Gemini Multimodal API 입력 형식으로 변환 및 데이터셋(JSONL) 파싱
   - 축사 모니터링 및 AI 학습용 라벨링 전처리

## 실행 방법

### 1. 가상환경 생성 및 패키지 설치

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env.example`을 복사하여 `.env` 생성 후 필요한 인자(ONVIF 주소, OCI 계정 정보, Gemini API Key)를 입력합니다.

```bash
cp .env.example .env
```

### 3. 서버 실행

```bash
uvicorn src.main:app --reload --port 8000
```

- API 문서는 `http://localhost:8000/docs` 에서 확인할 수 있습니다.

### 4. 테스트 실행

```bash
pytest
```
