"""Real-time Multi-Camera Pipeline Verification Tool for HoodyFarm.

Starts WorkerManager across all 9 barn cameras, monitors live ingestion,
verifies frames in real-time, saves snapshot samples, and produces diagnostic output.
"""

import os
import sys
import time
import cv2

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.domain.models.farm_profile import FarmProfile
from src.services.worker_manager import WorkerManager


def verify_all_cameras_live():
    yaml_path = "config/farms/hoodyfarm.yaml"
    print("=================================================================")
    print(" 📹 [후디팜 CCTV] 9개 채널 실시간 수집 및 멀티 채널 파이프라인 검증")
    print(f" 📄 설정 파일: {yaml_path}")
    print("=================================================================\n")

    profile = FarmProfile.from_yaml(yaml_path)
    print(f"농장명: {profile.farm_name} (ID: {profile.farm_id})")
    print(f"등록 카메라: {len(profile.cameras)}대")
    for cam in profile.cameras:
        print(f" - [{cam.camera_id}] {cam.name} -> {cam.rtsp_url}")

    print("\n🚀 [1/3] WorkerManager 멀티 카메라 오케스트레이터 초기화 및 전 채널 가동...")
    manager = WorkerManager(profile=profile)
    manager.start_all()

    snapshot_dir = os.path.join("captures", "live_check")
    os.makedirs(snapshot_dir, exist_ok=True)

    print("\n⏳ [2/3] 9개 채널 순차 웜업 및 실시간 스트림 수집 대기 (약 15초)...")
    time.sleep(15.0)

    print("\n🔍 [3/3] 9개 채널 실시간 수집 상태 및 최신 프레임 검증:")
    print("-" * 75)
    print(f"{'카메라 ID':<13} {'채널명':<16} {'수집 프레임':<11} {'해상도':<12} {'상태'}")
    print("-" * 75)

    all_success = True
    channel_results = {}

    for cam in profile.cameras:
        cid = cam.camera_id
        worker = manager.ingestion_workers.get(cid)
        if not worker:
            print(f"{cid:<13} {'(워커 없음)':<16} {'0':<11} {'N/A':<12} ❌ 워커 미생성")
            all_success = False
            continue

        # 최신 프레임 획득 시도
        frame = worker.get_latest_frame(timeout=1.0)
        # 만약 큐에서 못 꺼냈으면 링 버퍼에서 마지막 프레임 확인
        if frame is None and len(worker.ring_buffer) > 0:
            with worker._buffer_lock:
                frame = worker.ring_buffer[-1][0] if len(worker.ring_buffer) > 0 else None

        captured_count = worker.total_captured
        res_str = f"{frame.shape[1]}x{frame.shape[0]}" if frame is not None else "N/A"
        status_str = "✅ 실시간 수집 중" if (frame is not None and captured_count > 0) else "❌ 수집 실패"

        if frame is not None:
            save_path = os.path.join(snapshot_dir, f"{cid}.jpg")
            cv2.imwrite(save_path, frame)
            channel_results[cid] = {
                "name": cam.name,
                "captured": captured_count,
                "resolution": res_str,
                "snapshot": save_path,
                "success": True,
            }
        else:
            all_success = False
            channel_results[cid] = {
                "name": cam.name,
                "captured": captured_count,
                "resolution": "N/A",
                "snapshot": None,
                "success": False,
            }

        print(f"{cid:<13} {cam.name:<16} {captured_count:<11} {res_str:<12} {status_str}")

    print("-" * 75)

    print("\n🛑 파이프라인 안전 종료 중...")
    manager.stop_all()
    print("✅ 모든 워커 안전 종료 완료.\n")

    print("=================================================================")
    success_count = sum(1 for r in channel_results.values() if r["success"])
    print(f" 📊 최종 검증 결과: 9개 채널 중 {success_count}개 채널 실시간 수집 성공")
    if all_success:
        print(" 🎉 [성공] 9개 모든 축사 카메라가 실시간으로 프레임을 정상 획득하고 있습니다!")
        print(f" 🖼️ 스냅샷 저장 위치: {os.path.abspath(snapshot_dir)}")
    else:
        print(" ⚠️ [주의] 일부 채널에서 프레임 수집이 지연되거나 실패했습니다.")
    print("=================================================================")
    return all_success


if __name__ == "__main__":
    success = verify_all_cameras_live()
    sys.exit(0 if success else 1)
