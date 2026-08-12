import logging
from typing import Dict, Any, Optional, List
from src.config import settings

logger = logging.getLogger(__name__)

class ONVIFCameraService:
    """
    ONVIF Camera Service for SmartLife and standard ONVIF compliant CCTV cameras.
    Handles device discovery, media profiles, and RTSP stream URL extraction.
    Includes Dual-Fallback to RTSP_STREAM_URL if ONVIF is unreachable or unsupported.
    """
    def __init__(
        self, 
        host: Optional[str] = None, 
        port: Optional[int] = None, 
        user: Optional[str] = None, 
        pass_word: Optional[str] = None
    ):
        self.host = host or settings.ONVIF_HOST
        self.port = port or settings.ONVIF_PORT
        self.user = user or settings.ONVIF_USER
        self.password = pass_word or settings.ONVIF_PASSWORD
        self.device = None
        self.media_service = None
        self._connected = False

    def connect(self) -> bool:
        """
        Connect to camera via ONVIF protocol using onvif-zeep.
        """
        try:
            from onvif import ONVIFCamera
            logger.info(f"Connecting to ONVIF camera at {self.host}:{self.port}...")
            self.device = ONVIFCamera(
                self.host,
                self.port,
                self.user,
                self.password
            )
            self.media_service = self.device.create_media_service()
            self._connected = True
            logger.info(f"✅ Successfully connected to ONVIF camera at {self.host}:{self.port}")
            return True
        except ImportError:
            logger.warning("⚠️ onvif-zeep package not available. ONVIF fallback mode active.")
            self._connected = False
            return False
        except Exception as e:
            logger.warning(f"⚠️ Failed to connect to ONVIF camera at {self.host}:{self.port} - {e}")
            self._connected = False
            return False

    def get_profiles(self) -> List[Dict[str, Any]]:
        """
        Get list of media profiles from ONVIF camera.
        """
        if not self._connected:
            self.connect()

        if self.media_service:
            try:
                profiles = self.media_service.GetProfiles()
                return [
                    {
                        "name": getattr(p, "name", "Profile"),
                        "token": getattr(p, "token", f"token_{i}"),
                        "video_encoder": getattr(p.VideoEncoderConfiguration, "Encoding", "H264") if hasattr(p, "VideoEncoderConfiguration") and p.VideoEncoderConfiguration else "H264"
                    }
                    for i, p in enumerate(profiles)
                ]
            except Exception as e:
                logger.error(f"Error fetching media profiles: {e}")

        # Fallback profile list for testing / simulation
        return [
            {"name": "main_profile", "token": "profile_token_01", "video_encoder": "H264"},
            {"name": "sub_profile", "token": "profile_token_02", "video_encoder": "H264"}
        ]

    def get_stream_url(self, profile_token: Optional[str] = None) -> str:
        """
        Get RTSP Stream URI from ONVIF media service, with fallback to config RTSP_STREAM_URL.
        """
        if not self._connected:
            self.connect()

        if self.media_service:
            try:
                token = profile_token
                if not token:
                    profiles = self.get_profiles()
                    if profiles:
                        token = profiles[0]["token"]

                if token:
                    obj = self.media_service.create_type('GetStreamUri')
                    obj.StreamSetup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
                    obj.ProfileToken = token
                    res = self.media_service.GetStreamUri(obj)
                    if hasattr(res, 'Uri') and res.Uri:
                        logger.info(f"ONVIF Stream URI obtained: {res.Uri}")
                        return res.Uri
            except Exception as e:
                logger.warning(f"Failed to fetch stream URI via ONVIF: {e}")

        # Fallback to configured RTSP Stream URL
        fallback_url = settings.RTSP_STREAM_URL
        if not fallback_url or "your_cctv_password" in fallback_url:
            fallback_url = f"rtsp://{self.user}:{self.password}@{self.host}:554/stream1"
        
        logger.info(f"Using fallback RTSP Stream URL: {fallback_url}")
        return fallback_url

    def get_device_information(self) -> Dict[str, Any]:
        """
        Get camera model, firmware, serial number information.
        """
        if self.device:
            try:
                dev_info = self.device.devicemgmt.GetDeviceInformation()
                return {
                    "host": self.host,
                    "port": self.port,
                    "connected": True,
                    "manufacturer": getattr(dev_info, 'Manufacturer', 'SmartLife'),
                    "model": getattr(dev_info, 'Model', 'ONVIF-CCTV'),
                    "firmware_version": getattr(dev_info, 'FirmwareVersion', '1.0.0'),
                    "serial_number": getattr(dev_info, 'SerialNumber', 'SL-0001')
                }
            except Exception as e:
                logger.error(f"Error getting device information: {e}")

        return {
            "host": self.host,
            "port": self.port,
            "connected": self._connected,
            "manufacturer": "SmartLife ONVIF Camera",
            "model": "SL-CCTV-01",
            "firmware_version": "v1.0.0",
            "serial_number": "SL-DEMO-999"
        }
