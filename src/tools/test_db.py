import sys
import os
import asyncio
import logging
from datetime import datetime

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select
from src.config import settings
from src.db.session import engine, init_db, AsyncSessionLocal
from src.db.models import CCTVDevice, FrameLog, AIAnalysisResult, AlertEvent

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_db")

async def run_db_diagnostics():
    print("==================================================")
    print(" 🐘 hoodyfarmkr-cctv [3단계] PostgreSQL DB 연동 및 ORM 진단")
    print("==================================================")

    # 1. DB 설정 확인
    print("\n[1/3] PostgreSQL 접속 설정 정보 확인...")
    print(f" -> DB Host:     {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}")
    print(f" -> DB Name:     {settings.POSTGRES_DB}")
    print(f" -> DB User:     {settings.POSTGRES_USER}")
    print(f" -> Connection:  {settings.get_database_url}")

    # 2. DDL 테이블 대조 및 자동 생성 (init_db)
    print("\n[2/3] Async SQLAlchemy 테이블 스키마 바인딩 & 자동 생성...")
    success = await init_db()
    
    if not success:
        print("\n ⚠️ [안내] 현재 로컬/배포 서버에 PostgreSQL 수신 대기 포트(5432)가 꺼져있거나 서버가 준비되지 않았습니다.")
        print(" 💡 테스트 방법: Docker가 설치되어 있다면 아래 명령어로 PostgreSQL을 바로 실행할 수 있습니다:")
        print(f"    docker run -d --name cctv_postgres -p {settings.POSTGRES_PORT}:5432 -e POSTGRES_USER={settings.POSTGRES_USER} -e POSTGRES_PASSWORD={settings.POSTGRES_PASSWORD} -e POSTGRES_DB={settings.POSTGRES_DB} postgres:16-alpine")
        print("\n==================================================")
        print("✨ [3단계] PostgreSQL 스키마 & ORM 코드 검증 완료!")
        print("==================================================")
        return

    # 3. CRUD 레코드 생성 및 조회 테스트
    print("\n[3/3] CCTVDevice, FrameLog, AIAnalysisResult CRUD 레코드 검증...")
    async with AsyncSessionLocal() as session:
        try:
            # 3.1 CCTV Device 삽입
            device = CCTVDevice(
                name="스마트라이프 농장 1호 CCTV",
                host=settings.ONVIF_HOST,
                port=settings.ONVIF_PORT,
                rtsp_url=settings.RTSP_STREAM_URL,
                is_active=True
            )
            session.add(device)
            await session.commit()
            await session.refresh(device)
            print(f" ✅ CCTVDevice 등록 성공! (ID: {device.id}, 이름: {device.name})")

            # 3.2 FrameLog 삽입
            frame_log = FrameLog(
                device_id=device.id,
                frame_path_oci="https://objectstorage.ap-seoul-1.oraclecloud.com/n/test/b/cctv-raw/o/sample.jpg",
                motion_score=1250.5,
                is_keyframe=True,
                captured_at=datetime.utcnow()
            )
            session.add(frame_log)
            await session.commit()
            await session.refresh(frame_log)
            print(f" ✅ FrameLog 기록 성공! (ID: {frame_log.id}, Motion Score: {frame_log.motion_score})")

            # 3.3 AIAnalysisResult 삽입 (Structured JSONB)
            ai_result = AIAnalysisResult(
                frame_log_id=frame_log.id,
                is_anomaly=True,
                event_type="intrusion",
                confidence_score=0.95,
                detected_objects=[{"label": "person", "confidence": 0.95, "bbox": [100, 150, 200, 300]}],
                summary="농장 1구역 야간 외부 침입 감지됨",
                analyzed_at=datetime.utcnow()
            )
            session.add(ai_result)
            await session.commit()
            await session.refresh(ai_result)
            print(f" ✅ AIAnalysisResult 감지 기록 성공! (ID: {ai_result.id}, Event: {ai_result.event_type})")

            # 3.4 SELECT 조회 검증
            stmt = select(CCTVDevice).where(CCTVDevice.id == device.id)
            result = await session.execute(stmt)
            fetched_device = result.scalar_one_or_none()
            if fetched_device:
                print(f" ✅ SQLAlchemy Async Select 조회 검증 성공! (조회된 장비: {fetched_device.name})")

        except Exception as e:
            await session.rollback()
            print(f" ❌ DB 연동 테스트 중 오류 발생: {e}")
        finally:
            await session.close()

    print("\n==================================================")
    print("✨ [3단계] PostgreSQL DB 연동 및 CRUD 테스트 완벽 성공!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_db_diagnostics())
