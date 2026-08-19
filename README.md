# 📹 hoodyfarmkr-cctv

SmartLife CCTV (ONVIF/RTSP) 영상 수집, PostgreSQL DB 저장, OCI Cloud 파이프라인 & Gemini 2.5 Flash 멀티모달 AI 연동 파이프라인 서비스

---

## 📌 5단계 아키텍처 및 자가 진단 도구

본 프로젝트는 ONVIF 영상 수집부터 Docker/OCI 배포까지 5단계의 모듈화 구조로 개발되었습니다.

| 단계 | 모듈 및 역할 | 독립 자가 진단 실행 명령어 |
| :--- | :--- | :--- |
| **1단계** | 최상위 `.env` 환경 변수 관리 및 `config.py` 구성 | `python src/tools/check_env.py` |
| **2단계** | ONVIF Stream URI 획득, OpenCV RTSP 프레임 수집 & 모션 계산 | `python src/tools/test_stream.py` |
| **3단계** | PostgreSQL Async SQLAlchemy 2.0 ORM DB 연동 | `python src/tools/test_db.py` |
| **4단계** | Gemini 2.5 Flash API 연동 & Pydantic Structured Output | `python src/tools/test_gemini.py` |
| **5단계** | 파이프라인 통합 오케스트레이터 & Docker/OCI 배포 | `python src/tools/test_orchestrator.py` |
| **6단계** | Gemini 2.5 Flash 에러 자가 진단 및 코드 개선 (Self-Healing) | `python src/tools/test_code_refiner.py` (`npm run refine`) |

---

## 🚀 빠른 시작 (Quick Start)

### 1. 환경변수 설정
```bash
cp .env.example .env
```

### 2. 브랜치 전환 및 의존성 설치
```bash
nr branch feat/env
pip install -r requirements.txt
```

### 3. 전체 진단 및 FastAPI 서버 실행
```bash
# 통합 파이프라인 자가 진단
python src/tools/test_orchestrator.py

# 로컬 개발 서버 실행
npm run dev   # uvicorn src.main:app --reload --port 8000
```
* **Swagger API Documentation**: `http://localhost:8000/docs`

---

## 🐳 Docker Compose 및 OCI 서버 원클릭 배포 (5단계)

OCI(Oracle Cloud Infrastructure) Compute Instance에 **FastAPI 파이프라인 앱 + PostgreSQL 16 DB**를 한 번에 원클릭으로 컨테이너화하여 실행할 수 있습니다.

```bash
# Docker Compose 컨테이너 생성 및 백그라운드 구동
docker-compose up -d --build

# 컨테이너 상태 및 로그 확인
docker-compose ps
docker-compose logs -f cctv_app
```

---

## 🧪 TDD 단위 및 통합 테스트

```bash
# pytest 단위 테스트 전체 실행
npm run test
```
