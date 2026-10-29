"""Kontrol dua arah (FR-09): publish START/STOP/SET_CONFIG ke topic kontrol HP."""

import json
import uuid
from datetime import datetime


def build_control(command: str, config: dict | None = None,
                  now: datetime | None = None) -> tuple[dict, str]:
    """Rakit pesan kontrol; kembalikan (pesan, request_id).

    command: START | STOP | SET_CONFIG. SET_CONFIG wajib membawa config.
    """
    command = command.upper()
    if command not in ("START", "STOP", "SET_CONFIG"):
        raise ValueError(f"perintah tak dikenali: {command}")
    if command == "SET_CONFIG" and not config:
        raise ValueError("SET_CONFIG memerlukan config")

    request_id = f"req-{uuid.uuid4().hex[:12]}"
    message = {
        "command": command,
        "request_id": request_id,
        "timestamp": (now or datetime.now().astimezone()).isoformat(timespec="seconds"),
    }
    if config is not None:
        message["config"] = config
    return message, request_id


def publish_control(client, topic: str, command: str, config: dict | None = None) -> tuple[dict, str]:
    message, request_id = build_control(command, config)
    client.publish(topic, json.dumps(message), qos=1)
    return message, request_id


def parse_ack(payload: bytes | str) -> tuple[dict | None, str]:
    """Validasi ack dari HP (UC-05); kembalikan (ack, alasan_invalid)."""
    import json as _json
    try:
        ack = _json.loads(payload if isinstance(payload, str) else payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"ack bukan JSON valid: {exc}"
    if not isinstance(ack, dict):
        return None, "ack bukan objek JSON"
    for field in ("device_id", "request_id", "accepted"):
        if field not in ack:
            return None, f"field ack hilang: {field}"
    if not isinstance(ack["accepted"], bool):
        return None, "accepted harus boolean"
    return ack, ""
