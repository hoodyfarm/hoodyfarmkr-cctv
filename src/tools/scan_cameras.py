"""축사 CCTV 네트워크 실시간 ONVIF/ARP 스캔 및 YAML 자동 갱신 CLI 도구.

사용법:
    python -m src.tools.scan_cameras
    python -m src.tools.scan_cameras --update-yaml
    python -m src.tools.scan_cameras --subnet 192.168.0.0/24 --ports 80,8899
"""

import argparse
import asyncio
import os
import re
import shutil
import sys
from typing import Dict, List, Optional
import yaml

from src.services.network_scanner import (
    AsyncNetworkScanner,
    DiscoveredCamera,
    HARDWARE_MASTER_REGISTRY,
    normalize_mac,
)


def format_table(cameras: List[DiscoveredCamera]) -> str:
    """감지된 카메라 목록을 가독성 높은 텍스트 표로 포맷팅."""
    headers = ["No", "카메라 ID", "장비명", "MAC 주소", "예약 IP", "현재 감지 IP", "포트", "상태"]
    widths = [4, 13, 10, 19, 15, 15, 6, 12]

    border_line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    header_line = "| " + " | ".join(f"{h:<{w}}" for h, w in zip(headers, widths)) + " |"

    rows = [border_line, header_line, border_line]

    idx = 1
    for cam in cameras:
        status_display = cam.status
        if cam.status == "IP_SHIFTED":
            status_display = "⚡ IP_SHIFTED"
        elif cam.status == "NORMAL":
            status_display = "✅ NORMAL"
        elif cam.status == "OFFLINE":
            status_display = "❌ OFFLINE"

        current_ip = cam.current_ip or "-"
        default_ip = cam.default_ip or "-"

        row = [
            str(idx),
            cam.camera_id,
            cam.name,
            cam.mac or "-",
            default_ip,
            current_ip,
            str(cam.port),
            status_display,
        ]
        row_line = "| " + " | ".join(f"{col:<{w}}" for col, w in zip(row, widths)) + " |"
        rows.append(row_line)
        idx += 1

    rows.append(border_line)
    return "\n".join(rows)


def update_yaml_with_shifted_ips(
    cameras: List[DiscoveredCamera],
    yaml_path: str = "config/farms/hoodyfarm.yaml",
) -> int:
    """
    IP가 변경된(IP_SHIFTED) 카메라들의 RTSP URL을 YAML 파일에 반영하고 백업을 생성.
    갱신된 카메라 개수를 반환.
    """
    shifted = [c for c in cameras if c.status == "IP_SHIFTED" and c.current_ip]
    if not shifted:
        print("ℹ️ 변경된(IP_SHIFTED) 카메라가 없어 YAML 파일 갱신을 건너뜁니다.")
        return 0

    if not os.path.exists(yaml_path):
        print(f"⚠️ 설정 파일({yaml_path})을 찾을 수 없습니다.")
        return 0

    # 1. 백업 생성
    backup_path = f"{yaml_path}.bak"
    try:
        shutil.copy2(yaml_path, backup_path)
        print(f"📁 기존 설정 파일 백업 완료: {backup_path}")
    except Exception as e:
        print(f"⚠️ 백업 파일 생성 실패: {e}")

    # 2. YAML 로드
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    cam_list = data.get("cameras", [])
    updated_count = 0

    # 3. 변경 적용
    for sc in shifted:
        for entry in cam_list:
            if entry.get("camera_id") == sc.camera_id:
                old_url = entry.get("rtsp_url", "")
                # 정규식 치환: 구 IP를 새 IP로 치환
                # 예: rtsp://192.168.0.12/live/0/SUB -> rtsp://192.168.0.105/live/0/SUB
                # 또는 ${RTSP_STREAM_URL_CAM02:-rtsp://192.168.0.12/live/0/SUB}
                new_url = re.sub(
                    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
                    sc.current_ip,
                    old_url,
                )
                entry["rtsp_url"] = new_url
                updated_count += 1
                print(f"🔄 [{sc.camera_id}] URL 갱신: {old_url} ➔ {new_url}")

    # 4. 파일 저장
    if updated_count > 0:
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        print(f"✅ 총 {updated_count}대 카메라 IP 변경 사항이 {yaml_path}에 영구 저장되었습니다.")

    return updated_count


async def main_async(args: argparse.Namespace) -> int:
    ports = [int(p.strip()) for p in args.ports.split(",") if p.strip()]
    scanner = AsyncNetworkScanner(
        subnet=args.subnet,
        ports=ports,
        timeout=args.timeout,
    )

    print(f"🔍 축사 네트워크 스캔 시작: 서브넷={args.subnet}, 포트={ports}...")
    cameras = await scanner.scan_and_resolve()

    print("\n" + format_table(cameras) + "\n")

    shifted_count = sum(1 for c in cameras if c.status == "IP_SHIFTED")
    online_count = sum(1 for c in cameras if c.status in ("NORMAL", "IP_SHIFTED"))
    print(f"📊 스캔 통계: 전체 10대 중 {online_count}대 온라인, {shifted_count}대 IP 변경(밀림) 감지")

    if args.update_yaml:
        update_yaml_with_shifted_ips(cameras, yaml_path=args.yaml_path)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="축사 CCTV/NVR IP 이탈 자동 감지 및 ONVIF 고속 스캐너 CLI"
    )
    parser.add_argument(
        "--subnet",
        default="192.168.0.0/24",
        help="스캔 대상 축사 서브넷 대역 (기본: 192.168.0.0/24)",
    )
    parser.add_argument(
        "--ports",
        default="80,8899",
        help="스캔 대상 ONVIF 포트 (콤마 구분, 기본: 80,8899)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.8,
        help="단일 포트 연결 타임아웃 초 (기본: 0.8)",
    )
    parser.add_argument(
        "--update-yaml",
        action="store_true",
        help="IP 변경 감지 시 config/farms/hoodyfarm.yaml 자동 갱신",
    )
    parser.add_argument(
        "--yaml-path",
        default="config/farms/hoodyfarm.yaml",
        help="대상 설정 YAML 파일 경로 (기본: config/farms/hoodyfarm.yaml)",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
