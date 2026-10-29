"""Validasi pesan telemetri (FR-03, TC-04). Pesan invalid tidak pernah memicu alert."""

import re
from datetime import datetime

REQUIRED_FIELDS = ("device_id", "timestamp", "lux", "sound_level_relative",
                   "valid_light", "valid_audio", "simulation_mode")

_ISO_TZ = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def validate_message(payload: bytes | str) -> tuple[dict | None, str]:
    """Kembalikan (pesan, alasan). Pesan None berarti invalid dengan alasan."""
    try:
        message = _parse_json(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"payload bukan JSON valid: {exc}"

    if not isinstance(message, dict):
        return None, "payload bukan objek JSON"

    missing = [f for f in REQUIRED_FIELDS if f not in message]
    if missing:
        return None, f"field hilang: {', '.join(missing)}"

    if not isinstance(message["device_id"], str) or not message["device_id"]:
        return None, "device_id harus string tidak kosong"

    ts, reason = _parse_timestamp(message["timestamp"])
    if ts is None:
        return None, reason
    message["timestamp_parsed"] = ts

    for field in ("lux", "sound_level_relative"):
        value = message[field]
        if value is None:
            continue  # lux null boleh bila valid_light false (spec bagian 10)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"{field} harus numerik, dapat: {value!r}"

    sound = message["sound_level_relative"]
    if isinstance(sound, (int, float)) and not isinstance(sound, bool) and sound < 0:
        return None, f"sound_level_relative negatif: {sound}"

    for field in ("valid_light", "valid_audio", "simulation_mode"):
        if not isinstance(message[field], bool):
            return None, f"{field} harus boolean, dapat: {message[field]!r}"

    lux = message["lux"]
    if message["valid_light"] and (lux is None or not isinstance(lux, (int, float)) or isinstance(lux, bool)):
        return None, "valid_light true tetapi lux bukan numerik"
    if isinstance(lux, (int, float)) and not isinstance(lux, bool) and not 0 <= lux <= 200000:
        return None, f"lux di luar rentang wajar 0-200000: {lux}"

    return message, ""


def _parse_json(payload: bytes | str) -> object:
    import json
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if not payload.strip():
        raise ValueError("payload kosong")
    return json.loads(payload)


def _parse_timestamp(value: object) -> tuple[datetime | None, str]:
    if not isinstance(value, str) or not value:
        return None, "timestamp harus string ISO 8601"
    if not _ISO_TZ.search(value):
        return None, f"timestamp tanpa zona waktu: {value}"
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized), ""
    except ValueError:
        return None, f"timestamp tidak bisa diparse: {value}"
