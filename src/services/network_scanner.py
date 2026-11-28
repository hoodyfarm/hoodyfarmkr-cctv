"""ONVIF/ARP 기반 고속 비동기 네트워크 스캐너 및 장비 식별 모듈.

축사 서브넷(192.168.0.0/24) 내의 10대 마스터 장비(NVR 1대 + CCTV 9대)를
비동기 포트 스캔(80, 8899), ONVIF SOAP 프로브 및 ARP 캐시 테이블을 통해
1~2초 내에 탐색하고 MAC 주소 기반으로 1:1 대조 및 IP 변경(밀림)을 감지합니다.
"""

import asyncio
import ipaddress
import logging
import os
import re
import socket
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 10대 장비 하드웨어 식별자 마스터 대장 (SSOT)
# md/CCTV_NETWORK_RESERVATION.md 및 56호 명세서 기반
# -----------------------------------------------------------------------------
HARDWARE_MASTER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "5A-5A-00-A5-40-15": {
        "id": "NVR_CORE_01",
        "name": "cctvnvr",
        "description": "축사 전용 NVR 레코더",
        "default_ip": "192.168.0.2",
        "port": 80,
        "auth_required": False,
        "user": "",
        "rtsp_sub": "",
        "rtsp_main": "",
    },
    "4C-2F-7B-EE-9D-FD": {
        "id": "CAM_BARN_01",
        "name": "cctv1",
        "description": "1번사 (송아지방, Tuya)",
        "default_ip": "192.168.0.201",
        "port": 8899,
        "auth_required": True,
        "user": "admin",
        "rtsp_sub": "rtsp://{user}:{pw}@{ip}:554/streamtype=1",
        "rtsp_main": "rtsp://{user}:{pw}@{ip}:554/streamtype=0",
    },
    "5A-5A-00-A0-91-FD": {
        "id": "CAM_BARN_02",
        "name": "cctv2",
        "description": "2번사 (비육우, 모디아이)",
        "default_ip": "192.168.0.12",
        "port": 80,
        "auth_required": False,
        "user": "",
        "rtsp_sub": "rtsp://{ip}/live/0/SUB",
        "rtsp_main": "rtsp://{ip}/live/0/MAIN",
    },
    "5A-5A-00-A0-93-19": {
        "id": "CAM_BARN_03",
        "name": "cctv3",
        "description": "3번사 (번식우, 모디아이)",
        "default_ip": "192.168.0.13",
        "port": 80,
        "auth_required": False,
        "user": "",
        "rtsp_sub": "rtsp://{ip}/live/0/SUB",
        "rtsp_main": "rtsp://{ip}/live/0/MAIN",
    },
    "5A-5A-00-A0-93-26": {
        "id": "CAM_BARN_04",
        "name": "cctv4",
        "description": "4번사 (육성우, 모디아이)",
        "default_ip": "192.168.0.14",
        "port": 80,
        "auth_required": False,
        "user": "",
        "rtsp_sub": "rtsp://{ip}/live/0/SUB",
        "rtsp_main": "rtsp://{ip}/live/0/MAIN",
    },
    "5A-5A-00-A0-92-E6": {
        "id": "CAM_BARN_05",
        "name": "cctv5",
        "description": "5번사 (비육우, 모디아이)",
        "default_ip": "192.168.0.15",
        "port": 80,
        "auth_required": False,
        "user": "",
        "rtsp_sub": "rtsp://{ip}/live/0/SUB",
        "rtsp_main": "rtsp://{ip}/live/0/MAIN",
    },
    "5A-5A-00-A0-93-B8": {
        "id": "CAM_BARN_06",
        "name": "cctv6",
        "description": "6번사 (비육우, 모디아이)",
        "default_ip": "192.168.0.16",
        "port": 80,
        "auth_required": False,
        "user": "",
        "rtsp_sub": "rtsp://{ip}/live/0/SUB",
        "rtsp_main": "rtsp://{ip}/live/0/MAIN",
    },
    "5A-5A-00-3E-DC-20": {
        "id": "CAM_BARN_07",
        "name": "cctv7",
        "description": "7번사 (번식우, 모디아이)",
        "default_ip": "192.168.0.17",
        "port": 80,
        "auth_required": False,
        "user": "",
        "rtsp_sub": "rtsp://{ip}/live/0/SUB",
        "rtsp_main": "rtsp://{ip}/live/0/MAIN",
    },
    "5A-5A-00-AF-EA-4F": {
        "id": "CAM_BARN_08",
        "name": "cctv8",
        "description": "8번사 (번식우, 모디아이)",
        "default_ip": "192.168.0.18",
        "port": 80,
        "auth_required": False,
        "user": "",
        "rtsp_sub": "rtsp://{ip}/live/0/SUB",
        "rtsp_main": "rtsp://{ip}/live/0/MAIN",
    },
    "5A-5A-00-A0-93-BA": {
        "id": "CAM_BARN_09",
        "name": "cctv9",
        "description": "9번사 (퇴비사/외곽, 모디아이)",
        "default_ip": "192.168.0.19",
        "port": 80,
        "auth_required": False,
        "user": "",
        "rtsp_sub": "rtsp://{ip}/live/0/SUB",
        "rtsp_main": "rtsp://{ip}/live/0/MAIN",
    },
}

# ID 역방향 룩업 인덱스
CAMERA_ID_TO_MAC = {info["id"]: mac for mac, info in HARDWARE_MASTER_REGISTRY.items()}


def normalize_mac(mac: Optional[str]) -> str:
    """MAC 주소를 대문자 하이픈 형식(XX-XX-XX-XX-XX-XX)으로 표준화."""
    if not mac:
        return ""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()
    if len(cleaned) == 12:
        return "-".join(cleaned[i : i + 2] for i in range(0, 12, 2))
    return mac.strip().upper()


def get_arp_table(custom_output: Optional[str] = None) -> Dict[str, str]:
    """
    OS 시스템 ARP 테이블(Windows `arp -a`, Linux `/proc/net/arp` 또는 `arp -a`)을 파싱하여
    {ip: normalized_mac} 딕셔너리로 반환.
    """
    arp_map: Dict[str, str] = {}
    output = custom_output

    if output is None:
        # 1. Linux /proc/net/arp 확인
        if os.path.exists("/proc/net/arp"):
            try:
                with open("/proc/net/arp", "r", encoding="utf-8") as f:
                    for line in f.readlines()[1:]:
                        parts = line.split()
                        if len(parts) >= 4:
                            ip, _, _, mac = parts[0], parts[1], parts[2], parts[3]
                            if mac and mac != "00:00:00:00:00:00":
                                arp_map[ip] = normalize_mac(mac)
            except Exception as e:
                logger.debug(f"/proc/net/arp 읽기 실패: {e}")

        # 2. 시스템 arp -a 명령 실행
        if not arp_map:
            try:
                proc = subprocess.run(
                    ["arp", "-a"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    check=False,
                )
                output = proc.stdout
            except Exception as e:
                logger.warning(f"arp -a 명령 실행 중 오류: {e}")
                output = ""

    if output:
        # IP와 MAC 패턴 탐색 (Windows & Unix 형식 모두 매칭)
        # Windows: 192.168.0.12        5a-5a-00-a0-91-fd     dynamic
        # Unix:    ? (192.168.0.12) at 5a:5a:00:a0:91:fd [ether] on eth0
        pattern = re.compile(
            r"(\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b).*?([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})"
        )
        for line in output.splitlines():
            match = pattern.search(line)
            if match:
                ip_addr, mac_addr = match.group(1), match.group(2)
                arp_map[ip_addr] = normalize_mac(mac_addr)

    return arp_map


@dataclass
class DiscoveredCamera:
    """네트워크 스캔으로 감지된 카메라 및 NVR 장비 정보."""

    camera_id: str
    name: str
    mac: str
    current_ip: str
    default_ip: str
    port: int
    is_matched: bool
    is_ip_changed: bool
    status: str  # NORMAL, IP_SHIFTED, UNKNOWN_ONVIF, OFFLINE
    manufacturer: str = ""
    model: str = ""
    rtsp_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OnvifDeviceResolver:
    """ONVIF SOAP 프로브 요청 전송 및 기기 정보/MAC 추출기."""

    SOAP_GET_SYSTEM_DATE_AND_TIME = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
        "<s:Body><tds:GetSystemDateAndTime/></s:Body></s:Envelope>"
    )

    SOAP_GET_DEVICE_INFORMATION = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
        "<s:Body><tds:GetDeviceInformation/></s:Body></s:Envelope>"
    )

    @classmethod
    def probe_device(
        cls,
        ip: str,
        port: int,
        timeout: float = 1.0,
        path: str = "/onvif/device_service",
    ) -> Tuple[bool, Dict[str, str]]:
        """
        주어진 IP/포트로 ONVIF SOAP 요청을 전송하여 응답 여부 및 디바이스 메타데이터를 추출.
        """
        url = f"http://{ip}:{port}{path}"
        info: Dict[str, str] = {"ip": ip, "port": str(port)}

        # 1. GetSystemDateAndTime (인증 없이 대다수 지원)
        req = urllib.request.Request(
            url,
            data=cls.SOAP_GET_SYSTEM_DATE_AND_TIME.encode("utf-8"),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
                if status == 200:
                    info["onvif_alive"] = "true"
        except urllib.error.HTTPError as e:
            # 400, 401 등 HTTP 응답이 온 것 자체로 포트 및 ONVIF 서비스 생존 입증
            info["onvif_alive"] = "true"
            info["http_status"] = str(e.code)
        except Exception:
            # 연결 실패
            return False, info

        # 2. GetDeviceInformation 시도
        try:
            req_info = urllib.request.Request(
                url,
                data=cls.SOAP_GET_DEVICE_INFORMATION.encode("utf-8"),
                headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            )
            with urllib.request.urlopen(req_info, timeout=timeout) as resp:
                if resp.status == 200:
                    body = resp.read().decode("utf-8", errors="replace")
                    m_manu = re.search(r"<tds:Manufacturer>([^<]+)</tds:Manufacturer>", body)
                    m_model = re.search(r"<tds:Model>([^<]+)</tds:Model>", body)
                    m_serial = re.search(r"<tds:SerialNumber>([^<]+)</tds:SerialNumber>", body)
                    if m_manu:
                        info["manufacturer"] = m_manu.group(1).strip()
                    if m_model:
                        info["model"] = m_model.group(1).strip()
                    if m_serial:
                        info["serial"] = m_serial.group(1).strip()
        except Exception:
            pass

        return True, info


class AsyncNetworkScanner:
    """
    초고속 비동기 축사 서브넷 포트 스캐너 & 마스터 식별자 매칭 엔진.
    254개 IP를 1~2초 내에 스캔하여 실시간 장치 및 IP 밀림을 감지합니다.
    """

    def __init__(
        self,
        subnet: str = "192.168.0.0/24",
        ports: Optional[List[int]] = None,
        timeout: float = 0.8,
        concurrency_limit: int = 200,
    ):
        self.subnet = subnet
        self.ports = ports or [80, 8899]
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def check_port(self, ip: str, port: int) -> Optional[Tuple[str, int]]:
        """단일 IP:포트에 대해 TCP 연결 가능 여부를 비동기로 검사."""
        async with self.semaphore:
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port),
                    timeout=self.timeout,
                )
                writer.close()
                await writer.wait_closed()
                return (ip, port)
            except Exception:
                return None

    async def scan_open_ports(self) -> List[Tuple[str, int]]:
        """서브넷 내 모든 유효 호스트 IP의 타겟 포트 개방 여부를 동시 탐색."""
        network = ipaddress.ip_network(self.subnet, strict=False)
        tasks = []
        for host in network.hosts():
            ip_str = str(host)
            for port in self.ports:
                tasks.append(self.check_port(ip_str, port))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        open_targets: List[Tuple[str, int]] = [
            res for res in results if isinstance(res, tuple) and res is not None
        ]
        return open_targets

    async def scan_and_resolve(
        self,
        arp_cache_override: Optional[Dict[str, str]] = None,
        probe_override: Optional[Dict[Tuple[str, int], Tuple[bool, Dict[str, str]]]] = None,
    ) -> List[DiscoveredCamera]:
        """
        1. 254개 IP 포트 80/8899 비동기 고속 스캔
        2. 열린 포트에 ONVIF 프로브 호출 (ARP 테이블 갱신 유도)
        3. ARP 테이블에서 MAC 주소 획득
        4. HARDWARE_MASTER_REGISTRY 대조하여 DiscoveredCamera 생성
        """
        open_targets = await self.scan_open_ports()

        # 열린 포트들에 대해 ONVIF 프로브 비동기 실행 (I/O executor 활용)
        loop = asyncio.get_running_loop()
        probe_tasks = []

        for ip, port in open_targets:
            if probe_override and (ip, port) in probe_override:
                continue

            probe_tasks.append(
                loop.run_in_executor(
                    None,
                    OnvifDeviceResolver.probe_device,
                    ip,
                    port,
                    0.8,
                )
            )

        if probe_tasks:
            await asyncio.gather(*probe_tasks, return_exceptions=True)

        # 시스템 ARP 테이블 조회
        arp_table = arp_cache_override if arp_cache_override is not None else get_arp_table()

        discovered: List[DiscoveredCamera] = []
        detected_macs = set()

        for ip, port in open_targets:
            mac = arp_table.get(ip, "")
            manu = ""
            model = ""

            if probe_override and (ip, port) in probe_override:
                _, pinfo = probe_override[(ip, port)]
                manu = pinfo.get("manufacturer", "")
                model = pinfo.get("model", "")

            matched_entry = HARDWARE_MASTER_REGISTRY.get(mac)
            if matched_entry:
                camera_id = matched_entry["id"]
                name = matched_entry["name"]
                default_ip = matched_entry["default_ip"]
                is_changed = (ip != default_ip)
                status = "IP_SHIFTED" if is_changed else "NORMAL"
                rtsp_url = matched_entry["rtsp_sub"].format(
                    ip=ip, user=matched_entry.get("user", ""), pw="***"
                ) if matched_entry.get("rtsp_sub") else ""

                discovered.append(
                    DiscoveredCamera(
                        camera_id=camera_id,
                        name=name,
                        mac=mac,
                        current_ip=ip,
                        default_ip=default_ip,
                        port=port,
                        is_matched=True,
                        is_ip_changed=is_changed,
                        status=status,
                        manufacturer=manu,
                        model=model,
                        rtsp_url=rtsp_url,
                    )
                )
                detected_macs.add(mac)
            else:
                # 마스터 대장에 없는 미식별 ONVIF 장비
                discovered.append(
                    DiscoveredCamera(
                        camera_id=f"UNKNOWN_{ip.replace('.', '_')}",
                        name=f"unknown_device_{ip}",
                        mac=mac,
                        current_ip=ip,
                        default_ip="",
                        port=port,
                        is_matched=False,
                        is_ip_changed=False,
                        status="UNKNOWN_ONVIF",
                        manufacturer=manu,
                        model=model,
                        rtsp_url="",
                    )
                )

        # 마스터 대장 중 미감지된 기기도 OFFLINE 상태로 포함 (관제용 전수 테이블 제공)
        for mac, info in HARDWARE_MASTER_REGISTRY.items():
            if mac not in detected_macs:
                discovered.append(
                    DiscoveredCamera(
                        camera_id=info["id"],
                        name=info["name"],
                        mac=mac,
                        current_ip="",
                        default_ip=info["default_ip"],
                        port=info["port"],
                        is_matched=True,
                        is_ip_changed=False,
                        status="OFFLINE",
                        manufacturer="",
                        model="",
                        rtsp_url="",
                    )
                )

        # ID 순서 정렬
        discovered.sort(key=lambda d: d.camera_id)
        return discovered

    def resolve_camera_ip(
        self,
        camera_id_or_mac: str,
        arp_cache_override: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """특정 카메라 ID 또는 MAC으로 현재 감지된 활성 IP를 동기 방식으로 조회."""
        target_mac = ""
        # 1. camera_id로 등록되어 있는지 우선 확인
        if camera_id_or_mac in CAMERA_ID_TO_MAC:
            target_mac = CAMERA_ID_TO_MAC[camera_id_or_mac]
        else:
            # 2. MAC 주소 문자열인지 정규화 시도
            normalized = normalize_mac(camera_id_or_mac)
            if normalized in HARDWARE_MASTER_REGISTRY or len(normalized) == 17:
                target_mac = normalized

        if not target_mac:
            logger.warning(f"식별자를 찾을 수 없습니다: {camera_id_or_mac}")
            return None

        arp_table = arp_cache_override if arp_cache_override is not None else get_arp_table()
        # ARP 테이블에서 target_mac과 매칭되는 IP 탐색
        for ip, mac in arp_table.items():
            if normalize_mac(mac) == target_mac:
                return ip

        return None
