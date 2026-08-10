import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class ONVIFCameraService:
    """
    ONVIF Camera Service for SmartLife and standard ONVIF compliant CCTV cameras.
    Handles device discovery, media profiles, and RTSP stream URL extraction.
    """
    def __init__(self, host: str, port: int, user: str, pass_word: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = pass_word
        self.device = None
        self.media_service = None
        self._connected = False

    def connect(self) -> bool:
        """
        Connect to camera via ONVIF protocol using onvif-zeep.
        """
        try:
            from onvif import ONVIFCamera
            self.device = ONVIFCamera(
                self.host,
                self.port,
                self.user,
                self.password
            )
            self.media_service = self.device.create_media_service()
            self._connected = True
            logger.info(f"Successfully connected to ONVIF camera at {self.host}:{self.port}")
            return True
        except ImportError:
            logger.warning("onvif-zeep package not installed or available. Operating in simulation mode.")
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to ONVIF camera at {self.host}:{self.port} - {e}")
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
                        "name": p.name,
                        "token": p.token,
                        "video_encoder": p.VideoEncoderConfiguration.Encoding if hasattr(p, "VideoEncoderConfiguration") and p.VideoEncoderConfiguration else "H264"
                    }
                    for p in profiles
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
        Get RTSP Stream URI from ONVIF media service.
        """
        if not self._connected:
            self.connect()

        if self.media_service and profile_token:
            try:
                obj = self.media_service.create_type('GetStreamUri')
                obj.StreamSetup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
                obj.ProfileToken = profile_token
                res = self.media_service.GetStreamUri(obj)
                if hasattr(res, 'Uri'):
                    return res.Uri
            except Exception as e:
                logger.error(f"Failed to get ONVIF Stream URI: {e}")

        # Construct standard RTSP URI format for SmartLife cameras
        return f"rtsp://{self.user}:{self.password}@{self.host}:554/stream1"

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
