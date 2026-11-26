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

# 카메라 고정 IP (md/CCTV_NETWORK_RESERVATION.md 기준, 2026-11-26).
# NVR(192.168.0.2, MAC 5A-5A-00-A5-40-15)은 카메라가 아니므로 수집 대상에서 제외한다.
CAMERA_IPS = {
    "CAM_BARN_01": "192.168.0.201",  # 4C-2F-7B-EE-9D-FD
    "CAM_BARN_02": "192.168.0.12",   # 5A-5A-00-A0-91-FD
    "CAM_BARN_03": "192.168.0.13",   # 5A-5A-00-A0-93-19
    "CAM_BARN_04": "192.168.0.14",   # 5A-5A-00-A0-93-26
    "CAM_BARN_05": "192.168.0.15",   # 5A-5A-00-A0-92-E6
    "CAM_BARN_06": "192.168.0.16",   # 5A-5A-00-A0-93-B8
    "CAM_BARN_07": "192.168.0.17",   # 5A-5A-00-3E-DC-20
    "CAM_BARN_08": "192.168.0.18",   # 5A-5A-00-AF-EA-4F
    "CAM_BARN_09": "192.168.0.19",   # 5A-5A-00-A0-93-BA
}


def _build_default_cameras() -> List[Dict[str, str]]:
    """비밀번호는 코드에 두지 않고 .env(ONVIF_PASSWORD)에서 읽는다."""
    from urllib.parse import quote

    from src.config import settings

    user = getattr(settings, "ONVIF_USER", "admin")
    pw = quote(str(getattr(settings, "ONVIF_PASSWORD", "")), safe="")
    return [
        {
            "camera_id": cid,
            "ip": ip,
            "rtsp": f"rtsp://{user}:{pw}@{ip}:554/streamtype=1",
        }
        for cid, ip in CAMERA_IPS.items()
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
    cam_list = cameras or _build_default_cameras()
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
            print(f"[{cam_id}] 영상 수집 시도 ({cam['ip']})...", end=" ")

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
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="수집할 카메라 ID만 지정 (예: --only CAM_BARN_01). 미지정 시 전체 카메라",
    )
    args = parser.parse_args()

    selected = _build_default_cameras()
    if args.only:
        wanted = set(args.only)
        selected = [c for c in selected if c["camera_id"] in wanted]
        if not selected:
            raise SystemExit(f"--only 에 해당하는 카메라가 없습니다: {sorted(wanted)}")

    collect_dataset(
        output_dir=args.out_dir,
        interval_sec=args.interval,
        max_frames_per_cam=args.max_frames,
        cameras=selected,
    )
