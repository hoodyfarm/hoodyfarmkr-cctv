"""Automated Dataset Collector for HoodyFarm CCTV.

Captures raw CCTV frames across day/night timeframes to build
datasets for fine-tuning YOLO cattle behavior models.
"""

import argparse
import datetime
import os
import time
from typing import Dict, List, Optional

import cv2
import yaml

DEFAULT_CAMERAS = [
    {"camera_id": "CAM_01", "ip": "192.168.0.51", "rtsp": "rtsp://admin:wlsvndqoR1!@192.168.0.51:554/streamtype=1"},
    {"camera_id": "CAM_02", "ip": "192.168.0.52", "rtsp": "rtsp://admin:wlsvndqoR1!@192.168.0.52:554/streamtype=1"},
    {"camera_id": "CAM_03", "ip": "192.168.0.53", "rtsp": "rtsp://admin:wlsvndqoR1!@192.168.0.53:554/streamtype=1"},
    {"camera_id": "CAM_04", "ip": "192.168.0.54", "rtsp": "rtsp://admin:wlsvndqoR1!@192.168.0.54:554/streamtype=1"},
    {"camera_id": "CAM_05", "ip": "192.168.0.55", "rtsp": "rtsp://admin:wlsvndqoR1!@192.168.0.55:554/streamtype=1"},
    {"camera_id": "CAM_06", "ip": "192.168.0.56", "rtsp": "rtsp://admin:wlsvndqoR1!@192.168.0.56:554/streamtype=1"},
    {"camera_id": "CAM_07", "ip": "192.168.0.57", "rtsp": "rtsp://admin:wlsvndqoR1!@192.168.0.57:554/streamtype=1"},
    {"camera_id": "CAM_08", "ip": "192.168.0.58", "rtsp": "rtsp://admin:wlsvndqoR1!@192.168.0.58:554/streamtype=1"},
    {"camera_id": "CAM_09", "ip": "192.168.0.59", "rtsp": "rtsp://admin:wlsvndqoR1!@192.168.0.59:554/streamtype=1"},
    {"camera_id": "CAM_10", "ip": "192.168.0.60", "rtsp": "rtsp://admin:wlsvndqoR1!@192.168.0.60:554/streamtype=1"},
]


def get_time_category() -> str:
    """Classify current time into time categories for lighting diversity."""
    hour = datetime.datetime.now().hour
    if 6 <= hour < 11:
        return "morning"
    elif 11 <= hour < 17:
        return "day"
    elif 17 <= hour < 20:
        return "evening"
    else:
        return "night_ir"


def capture_single_frame(rtsp_url: str, timeout_sec: float = 3.0) -> Optional[cv2.Mat]:
    """Capture a single frame from RTSP stream with timeout."""
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;3000000|rtsp_transport;tcp"
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return None

    ret, frame = cap.read()
    cap.release()
    return frame if ret and frame is not None and frame.size > 0 else None


def collect_dataset(
    output_dir: str = "datasets/raw_frames",
    interval_sec: float = 15.0,
    max_frames_per_cam: int = 100,
    cameras: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, int]:
    """Collects frames from cameras in a round-robin loop."""
    cam_list = cameras or DEFAULT_CAMERAS
    os.makedirs(output_dir, exist_ok=True)
    stats: Dict[str, int] = {cam["camera_id"]: 0 for cam in cam_list}

    print("====================================================")
    print("📸 [후디팜 CCTV] 축사 행동인식용 데이터셋 자동 수집기")
    print(f"📁 저장 경로: {os.path.abspath(output_dir)}")
    print(f"⏱️ 수집 주기: {interval_sec}초 / 카메라당 목표: {max_frames_per_cam}장")
    print("====================================================")

    total_captured = 0
    cycle = 0

    while True:
        cycle += 1
        active_any = False
        time_cat = get_time_category()

        for cam in cam_list:
            cam_id = cam["camera_id"]
            if stats[cam_id] >= max_frames_per_cam:
                continue

            active_any = True
            rtsp = cam["rtsp"]
            print(f"[{cam_id}] 영상 수집 시도 ({rtsp})...", end=" ")

            frame = capture_single_frame(rtsp)
            if frame is not None:
                ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{cam_id}_{time_cat}_{ts_str}_{stats[cam_id]:04d}.jpg"
                save_path = os.path.join(output_dir, filename)
                cv2.imwrite(save_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                stats[cam_id] += 1
                total_captured += 1
                print(f"✅ 저장 완료 ({stats[cam_id]}/{max_frames_per_cam})")
            else:
                print("❌ 연결 대기 (카메라 오프라인 또는 응답 없음)")

        if not active_any:
            print("\n🎉 모든 카메라의 목표 수집량이 완료되었습니다!")
            break

        print(f"\n[대기] {interval_sec}초 후 다음 수집 사이클 ({total_captured}장 수집됨)...")
        time.sleep(interval_sec)

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HoodyFarm CCTV Dataset Collector")
    parser.add_argument("--out-dir", default="datasets/raw_frames", help="Output directory")
    parser.add_argument("--interval", type=float, default=15.0, help="Interval seconds between captures")
    parser.add_argument("--max-frames", type=int, default=100, help="Max frames per camera")
    args = parser.parse_args()

    collect_dataset(
        output_dir=args.out_dir,
        interval_sec=args.interval,
        max_frames_per_cam=args.max_frames,
    )
