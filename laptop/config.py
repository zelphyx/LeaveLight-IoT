"""Konfigurasi bersama LeaveLight dari .env (dibaca via python-dotenv atau parser manual)."""

import os
from pathlib import Path


def _parse_env_file(path: Path) -> dict:
    """Parser .env sederhana: KEY=VALUE, abaikan komentar dan baris kosong."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def load_config(env_file: str | None = None) -> dict:
    """Muat konfigurasi: .env dikalahkan oleh environment variable yang sudah ada."""
    path = Path(env_file or os.environ.get("LEAVELIGHT_ENV", ".env"))
    config = _parse_env_file(path)
    config.update({k: v for k, v in os.environ.items() if k in _KEYS})

    # Alias MQTT_HOST -> HIVEMQ_CLUSTER_URL, MQTT_PORT -> HIVEMQ_PORT
    if config.get("MQTT_HOST") and not config.get("HIVEMQ_CLUSTER_URL"):
        config["HIVEMQ_CLUSTER_URL"] = config["MQTT_HOST"]
    if config.get("MQTT_PORT") and not config.get("HIVEMQ_PORT"):
        config["HIVEMQ_PORT"] = config["MQTT_PORT"]
    if config.get("MQTT_USERNAME") and not config.get("HIVEMQ_USERNAME"):
        config["HIVEMQ_USERNAME"] = config["MQTT_USERNAME"]
    if config.get("MQTT_PASSWORD") and not config.get("HIVEMQ_PASSWORD"):
        config["HIVEMQ_PASSWORD"] = config["MQTT_PASSWORD"]

    # Bila masih memakai placeholder yourcluster, alihkan ke public broker agar tidak Not authorized
    cluster_url = config.get("HIVEMQ_CLUSTER_URL", "")
    if not cluster_url or "yourcluster" in cluster_url:
        config["HIVEMQ_CLUSTER_URL"] = config.get("MQTT_HOST") or "broker.hivemq.com"

    defaults = _defaults()
    merged = {**defaults, **{k: v for k, v in config.items() if v != ""}}
    return _coerce(merged)


def _defaults() -> dict:
    return {
        "HIVEMQ_CLUSTER_URL": "broker.hivemq.com",
        "HIVEMQ_PORT": "8883",
        "HIVEMQ_USERNAME": "",
        "HIVEMQ_PASSWORD": "",
        "PROJECT_ID": "projek1",
        "DEVICE_ID": "leavelight_phone01",
        "INTERVAL_S": "10",
        "LUX_THRESHOLD": "150",
        "SOUND_THRESHOLD": "0.05",
        "CONFIRMATION_WINDOW": "3",
        "DATA_TIMEOUT_S": "30",
        "SCHEDULE_START": "17:30",
        "SCHEDULE_END": "22:00",
        "LIGHT_SENSOR_NAME": "",
        "MQTT_TLS": "true",
    }


_KEYS = set(_defaults()) | {"MQTT_HOST", "MQTT_PORT", "MQTT_USERNAME", "MQTT_PASSWORD", "MQTT_TLS"}


def _coerce(config: dict) -> dict:
    for key in ("HIVEMQ_PORT", "INTERVAL_S", "CONFIRMATION_WINDOW", "DATA_TIMEOUT_S"):
        config[key] = int(float(config[key]))
    config["LUX_THRESHOLD"] = float(config["LUX_THRESHOLD"])
    config["SOUND_THRESHOLD"] = float(config["SOUND_THRESHOLD"])
    return config


def topics(config: dict) -> dict:
    """Topic MQTT sesuai spec bagian 4."""
    base = f"leavelight/{config['PROJECT_ID']}"
    device = config["DEVICE_ID"]
    return {
        "telemetry": f"{base}/telemetry",
        "control": f"{base}/control/{device}",
        "ack": f"{base}/ack/{device}",
    }
