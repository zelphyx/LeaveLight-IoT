"""Test validasi telemetri sesuai FR-03 dan TC-04 spec LeaveLight."""

import json
import pytest
import sys
from pathlib import Path

# Add laptop to path
sys.path.insert(0, str(Path(__file__).parent.parent / "laptop"))
from validate import validate_message


def _valid_payload():
    return {
        "device_id": "leavelight_phone01",
        "timestamp": "2026-10-29T18:30:00+07:00",
        "lux": 145.0,
        "sound_level_relative": 0.082,
        "valid_light": True,
        "valid_audio": True,
        "simulation_mode": False,
    }


def test_valid_message_passes():
    payload = json.dumps(_valid_payload()).encode("utf-8")
    msg, reason = validate_message(payload)
    assert msg is not None
    assert reason == ""
    assert msg["device_id"] == "leavelight_phone01"
    assert msg["lux"] == 145.0
    assert msg["timestamp_parsed"].tzinfo is not None


def test_reject_empty_payload():
    msg, reason = validate_message(b"")
    assert msg is None
    assert "payload bukan JSON valid" in reason


def test_reject_missing_required_field():
    raw = _valid_payload()
    del raw["sound_level_relative"]
    msg, reason = validate_message(json.dumps(raw))
    assert msg is None
    assert "field hilang" in reason


def test_reject_non_numeric_lux():
    raw = _valid_payload()
    raw["lux"] = "terang_sekali"
    msg, reason = validate_message(json.dumps(raw))
    assert msg is None
    assert "lux harus numerik" in reason


def test_reject_negative_sound():
    raw = _valid_payload()
    raw["sound_level_relative"] = -0.05
    msg, reason = validate_message(json.dumps(raw))
    assert msg is None
    assert "sound_level_relative negatif" in reason


def test_reject_timestamp_without_tz():
    raw = _valid_payload()
    raw["timestamp"] = "2026-10-29T18:30:00"
    msg, reason = validate_message(json.dumps(raw))
    assert msg is None
    assert "timestamp tanpa zona waktu" in reason


def test_allow_null_lux_when_valid_light_false():
    raw = _valid_payload()
    raw["lux"] = None
    raw["valid_light"] = False
    msg, reason = validate_message(json.dumps(raw))
    assert msg is not None
    assert msg["valid_light"] is False
    assert msg["lux"] is None
