"""Pipeline laptop (edge 2): validasi -> smoothing -> rule engine -> simpan.

Menyediakan objek Pipeline dengan state untuk dashboard Flask.
Jalankan dengan: python main.py [--env .env]
"""

import argparse
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path

# Pastikan folder laptop dan folder root terdaftar di sys.path
_repo_root = Path(__file__).resolve().parent.parent
_laptop_dir = Path(__file__).resolve().parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
if str(_laptop_dir) not in sys.path:
    sys.path.insert(0, str(_laptop_dir))

# Auto-load packages dari local .venv jika ada
for _sp in _repo_root.glob(".venv/lib/python*/site-packages"):
    if str(_sp) not in sys.path:
        sys.path.insert(0, str(_sp))

from config import load_config, topics
from mqtt_sub import MqttSub
from rule_engine import PERIKSA_RUANGAN, RuleEngine
from smoothing import LuxSmoother
from store import Store
from validate import validate_message

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, config: dict, data_dir: str = "data"):
        self.config = config
        self.t = topics(config)
        self.store = Store(data_dir)
        self.rules = RuleEngine(
            lux_threshold=config["LUX_THRESHOLD"],
            sound_threshold=config["SOUND_THRESHOLD"],
            confirmation_window=config["CONFIRMATION_WINDOW"],
            data_timeout_s=config["DATA_TIMEOUT_S"],
            schedule_start=config["SCHEDULE_START"],
            schedule_end=config["SCHEDULE_END"],
        )
        self.smoother = LuxSmoother(window=3)
        self.lock = threading.Lock()
        self.mqtt: MqttSub | None = None
        self.latest: dict | None = None  # status terbaru untuk GET /api/status
        self.received_count = 0
        self.invalid_count = 0

    def handle_telemetry(self, payload: bytes, received_at: datetime) -> None:
        message, reason = validate_message(payload)
        with self.lock:
            self.received_count += 1
            if message is None:
                self.invalid_count += 1
                self.latest = {
                    "received_at": received_at.isoformat(timespec="seconds"),
                    "status": "SENSOR/KONEKSI BERMASALAH",
                    "reason": reason, "valid": False,
                }
                log.warning("pesan invalid: %s", reason)
                return

            lux_smooth = self.smoother.add(message["lux"])
            status, rule_reason, make_event = self.rules.evaluate(message, received_at)
            event_id = None
            if make_event:
                event_id = self.store.save_event(message, received_at, rule_reason)
                log.warning("PERIKSA RUANGAN event#%d: %s", event_id, rule_reason)

            self.store.save_telemetry(message, received_at, lux_smooth, status, rule_reason)
            self.latest = {
                "received_at": received_at.isoformat(timespec="seconds"),
                "device_id": message["device_id"],
                "lux": message["lux"],
                "lux_smooth": lux_smooth,
                "sound_level_relative": message["sound_level_relative"],
                "valid_light": message["valid_light"],
                "valid_audio": message["valid_audio"],
                "simulation_mode": message["simulation_mode"],
                "status": status,
                "reason": rule_reason,
                "event_id": event_id,
                "streak": self.rules.streak,
                "schedule": f"{self.config['SCHEDULE_START']}-{self.config['SCHEDULE_END']}",
            }

    def drain_acks(self) -> list[dict]:
        if self.mqtt is None:
            return []
        return self.mqtt.drain_acks()


def _is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="LeaveLight laptop edge")
    parser.add_argument("--port", type=int, default=5000, help="port dashboard (default 5000)")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--no-mqtt", action="store_true",
                        help="jalankan tanpa broker (mode uji dashboard)")
    args = parser.parse_args()

    config = load_config(args.env)
    pipeline = Pipeline(config)

    if args.no_mqtt:
        log.info("mode tanpa broker; dashboard bisa diuji memakai data simulator")
    else:
        mqtt_sub = MqttSub(config)
        mqtt_sub.telemetry_handler = pipeline.handle_telemetry
        mqtt_sub.start()
        pipeline.mqtt = mqtt_sub
        log.info("pipeline jalan, kirim telemetri ke %s lalu buka dashboard", pipeline.t["telemetry"])

    port = args.port
    if port == 5000 and _is_port_in_use(5000):
        log.warning("Port 5000 sedang digunakan (AirPlay Receiver di macOS). Mengalihkan dashboard otomatis ke port 5001.")
        port = 5001

    from dashboard.app import create_app
    app = create_app(pipeline)
    try:
        app.run(host="0.0.0.0", port=port)
    finally:
        if pipeline.mqtt is not None:
            pipeline.mqtt.stop()


if __name__ == "__main__":
    main()
