"""Pembacaan sensor cahaya via Termux:API (FR-01, TC-01).

Menjalankan termux-sensor -l untuk deteksi otomatis nama sensor cahaya,
dan termux-sensor -n 1 -s <name> untuk pembacaan berkala.
"""

import json
import logging
import shutil
import subprocess

log = logging.getLogger(__name__)


def is_termux_sensor_available() -> bool:
    return shutil.which("termux-sensor") is not None


def detect_light_sensor() -> str | None:
    """Deteksi nama sensor cahaya dari output `termux-sensor -l`."""
    if not is_termux_sensor_available():
        log.warning("termux-sensor tidak ditemukan di PATH")
        return None
    try:
        proc = subprocess.run(
            ["termux-sensor", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True
        )
        data = json.loads(proc.stdout)
        sensors = data.get("sensors", [])
        for s in sensors:
            name = s.get("name", "")
            stype = str(s.get("type", "")).lower()
            if "light" in name.lower() or "light" in stype or s.get("type") == 5:
                return name
        return None
    except Exception as exc:
        log.warning("gagal deteksi sensor cahaya: %s", exc)
        return None


def read_light(sensor_name: str | None = None) -> tuple[float | None, bool]:
    """Baca satu sampel lux. Kembalikan (lux, valid_light)."""
    if not is_termux_sensor_available():
        return None, False

    cmd = ["termux-sensor", "-n", "1"]
    if sensor_name:
        cmd.extend(["-s", sensor_name])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
        if proc.returncode != 0 or not proc.stdout.strip():
            return None, False

        data = json.loads(proc.stdout)
        # Termux:API format: {"sensor_name": {"values": [val, ...]}}
        # atau langsung dict sensor
        for k, v in data.items():
            if isinstance(v, dict) and "values" in v and v["values"]:
                raw_val = v["values"][0]
                lux = float(raw_val)
                if 0 <= lux <= 200000:
                    return lux, True
                else:
                    log.warning("lux di luar rentang: %f", lux)
                    return None, False
        return None, False
    except Exception as exc:
        log.warning("gagal membaca sensor cahaya: %s", exc)
        return None, False
