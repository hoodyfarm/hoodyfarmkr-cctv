"""ONVIF 간이 프로브 (읽기 전용 요청만 전송, 외부 의존성 없음).

사용 예:
  python -m src.tools.onvif_probe 192.168.0.12 --port 80
  python -m src.tools.onvif_probe 192.168.0.201 --port 8899
  python -m src.tools.onvif_probe 192.168.0.12 --port 80 --user admin --password ""

확인 항목:
  1. GetSystemDateAndTime  (ONVIF 규격상 인증 없이 허용되는 호출 → 엔드포인트 생존 확인)
  2. GetCapabilities       (인증 없이 되는지 여부)
  3. GetProfiles           (보통 인증 필요 → 비밀번호 요구 여부 판별)
  4. GetStreamUri          (RTSP 주소 획득)
"""

import argparse
import base64
import datetime
import hashlib
import os
import re
import urllib.error
import urllib.request

NS = (
    'xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
    'xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
    'xmlns:tt="http://www.onvif.org/ver10/schema"'
)


def _security_header(user: str, password: str) -> str:
    """WS-UsernameToken (PasswordDigest) 헤더. 빈 비밀번호도 그대로 계산한다."""
    nonce = os.urandom(16)
    created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = base64.b64encode(
        hashlib.sha1(nonce + created.encode() + password.encode()).digest()
    ).decode()
    return (
        '<s:Header><Security s:mustUnderstand="1" '
        'xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        f"<UsernameToken><Username>{user}</Username>"
        '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
        f"{digest}</Password>"
        f'<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
        f"{base64.b64encode(nonce).decode()}</Nonce>"
        '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        f"{created}</Created></UsernameToken></Security></s:Header>"
    )


def soap_call(url: str, body: str, user: str = None, password: str = None, timeout: float = 5.0):
    header = _security_header(user, password) if user is not None else ""
    envelope = f'<?xml version="1.0" encoding="utf-8"?><s:Envelope {NS}>{header}<s:Body>{body}</s:Body></s:Envelope>'
    req = urllib.request.Request(
        url,
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:  # 연결 실패 등
        return None, str(e)


def verdict(status, text: str) -> str:
    if status is None:
        return f"연결 실패: {text}"
    if status == 200 and "Fault" not in text:
        return "OK (인증 없이/제공한 자격으로 성공)"
    if status in (400, 401, 403) or "NotAuthorized" in text or "Sender not Authorized" in text:
        return f"인증 필요 (HTTP {status})"
    return f"HTTP {status} / " + re.sub(r"\s+", " ", text)[:160]


def probe(host: str, port: int, user: str = None, password: str = None, path: str = "/onvif/device_service"):
    url = f"http://{host}:{port}{path}"
    mode = "인증 없음" if user is None else f"user={user!r}, password={'(빈값)' if password == '' else '***'}"
    print(f"== ONVIF 프로브: {url}  [{mode}]")

    tests = [
        ("GetSystemDateAndTime", "<tds:GetSystemDateAndTime/>", False),
        ("GetCapabilities", "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>", True),
    ]
    for name, body, use_auth in tests:
        status, text = soap_call(url, body, user if use_auth else None, password if use_auth else None)
        print(f"  {name:<22} -> {verdict(status, text)}")
        if name == "GetCapabilities" and status == 200:
            m = re.search(r"<tt:XAddr>(http[^<]*media[^<]*)</tt:XAddr>", text, re.I)
            if m:
                print(f"    media 서비스 주소: {m.group(1)}")

    media_url = url
    status, text = soap_call(url, "<trt:GetProfiles/>", user, password)
    print(f"  {'GetProfiles':<22} -> {verdict(status, text)}")
    tokens = re.findall(r'<trt:Profiles[^>]*token="([^"]+)"', text) or re.findall(r'Profiles[^>]*token="([^"]+)"', text)
    for tok in tokens[:3]:
        body = (
            "<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream>"
            "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>"
            f"<trt:ProfileToken>{tok}</trt:ProfileToken></trt:GetStreamUri>"
        )
        st, tx = soap_call(media_url, body, user, password)
        m = re.search(r"<tt:Uri>([^<]+)</tt:Uri>", tx)
        print(f"  GetStreamUri[{tok}] -> {m.group(1) if m else verdict(st, tx)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ONVIF read-only probe")
    ap.add_argument("host")
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--user", default=None, help="지정 시 WS-UsernameToken 인증으로 호출")
    ap.add_argument("--password", default="", help="빈 문자열 허용")
    ap.add_argument("--path", default="/onvif/device_service")
    a = ap.parse_args()
    probe(a.host, a.port, a.user, a.password if a.user is not None else None, a.path)
