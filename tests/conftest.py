import pytest
import numpy as np
import cv2
from fastapi.testclient import TestClient
from src.main import app

@pytest.fixture
def client():
    """
    FastAPI TestClient Fixture for Integration Testing.
    """
    return TestClient(app)

@pytest.fixture
def mock_bgr_frame():
    """
    Generates a 720p synthetic BGR image frame for OpenCV/Refiner testing.
    """
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.putText(img, "TDD Test Frame", (400, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
    return img

@pytest.fixture
def mock_jpeg_bytes(mock_bgr_frame):
    """
    Generates JPEG encoded byte data from synthetic frame.
    """
    _, buffer = cv2.imencode('.jpg', mock_bgr_frame)
    return buffer.tobytes()

@pytest.fixture
def mock_onvif_credentials():
    return {
        "host": "192.168.1.100",
        "port": 80,
        "user": "admin",
        "password": "test_password"
    }
