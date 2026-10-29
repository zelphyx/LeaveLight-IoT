"""Test endpoint Dashboard Flask LeaveLight (spec bagian 7)."""

import json
import pytest
import sys
from pathlib import Path

# Add project root and laptop to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "laptop"))

from config import load_config
from dashboard.app import create_app
from laptop.main import Pipeline


@pytest.fixture
def client(tmp_path):
    config = load_config()
    pipeline = Pipeline(config, data_dir=str(tmp_path / "data"))
    app = create_app(pipeline)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client, pipeline


def test_index_page(client):
    c, _ = client
    res = c.get("/")
    assert res.status_code == 200
    assert "LeaveLight IoT" in res.text
    assert "telemetryChart" in res.text


def test_api_status(client):
    c, _ = client
    res = c.get("/api/status")
    assert res.status_code == 200
    data = res.get_json()
    assert "broker" in data
    assert "received" in data
    assert "invalid" in data


def test_api_history(client):
    c, _ = client
    res = c.get("/api/history")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)


def test_api_events(client):
    c, _ = client
    res = c.get("/api/events")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)


def test_api_config_update(client):
    c, pipeline = client
    patch = {
        "LUX_THRESHOLD": 180.0,
        "SOUND_THRESHOLD": 0.04,
        "SCHEDULE_START": "18:00",
        "SCHEDULE_END": "21:30"
    }
    res = c.post("/api/config", json=patch)
    assert res.status_code == 200
    data = res.get_json()
    assert data["config"]["LUX_THRESHOLD"] == 180.0
    assert pipeline.config["LUX_THRESHOLD"] == 180.0
    assert pipeline.rules.lux_threshold == 180.0


def test_api_control_validation(client):
    c, _ = client
    # Command invalid
    res = c.post("/api/control", json={"command": "REBOOT"})
    assert res.status_code == 400
    assert "START atau STOP" in res.get_json()["error"]
