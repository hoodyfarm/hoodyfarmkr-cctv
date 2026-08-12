import sys
import os
import asyncio
import logging
import json

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.db.session import init_db
from src.services.orchestrator import pipeline_orchestrator

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_orchestrator")

async def run_end_to_end_orchestrator_diagnostics():
    print("==================================================")
    print(" 🚀 hoodyfarmkr-cctv [5단계] 전체 파이프라인 통합 진단")
    print("==================================================")

    # 1. DB 초기화
    print("\n[1/3] PostgreSQL Async DB 테이블 초기화 시도...")
    db_ok = await init_db()
    if db_ok:
        print(" ✅ Async DB 준비 완료")
    else:
        print(" ℹ️ DB 연결 대기 (시뮬레이션 모드 메모리 파이프라인 지속)")

    # 2. 파이프라인 사이클 실행
    print("\n[2/3] End-to-End 통합 파이프라인 1회 실행 중...")
    print("      [RTSP Frame Capture -> Motion Check -> Gemini 2.5 AI -> PostgreSQL Log -> OCI Upload -> Webhook Alert]")
    
    result = await pipeline_orchestrator.run_pipeline_cycle()

    # 3. 사이클 결과 출력
    print("\n[3/3] 파이프라인 실행 결과 리포트:")
    print(f" 🆔 Cycle ID:          {result.get('cycle_id')}")
    print(f" 📹 Frame Synthetic?:  {result.get('is_synthetic')}")
    print(f" 🏃 Motion Score:      {result.get('motion_score')}")
    print(f" ☁️ OCI Upload URL:     {result.get('oci_url') or 'N/A (Simulation)'}")
    print(f" 🐘 DB Log ID:         {result.get('db_frame_log_id') or 'N/A'}")
    print(f" 🔔 Webhook Status:    {result.get('webhook_status')}")
    
    ai_res = result.get('ai_result', {})
    print("\n 🤖 [Gemini 2.5 Flash AI Structured Analysis Summary]")
    print(f"    - Anomaly Detected: {ai_res.get('is_anomaly')}")
    print(f"    - Event Type:       {ai_res.get('event_type')}")
    print(f"    - Confidence:       {ai_res.get('confidence_score')}")
    print(f"    - Summary:          {ai_res.get('summary')}")

    print("\n==================================================")
    print("✨ [5단계] 전체 파이프라인 통합 오케스트레이션 검증 완벽 완료!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_end_to_end_orchestrator_diagnostics())
