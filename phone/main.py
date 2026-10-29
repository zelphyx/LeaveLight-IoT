"""Loop utama HP (edge 1) LeaveLight (spec bagian 3, 4, 5).

Membaca sensor cahaya, merekam segmen audio 3s untuk RMS,
melakukan smoothing lokal lux, merakit JSON telemetri,
dan menerima perintah kontrol START/STOP/SET_CONFIG via MQTT.
"""

import argparse
import logging
import sys
import time
from collections import deque
from datetime import datetime

from audio import measure_sound_level_relative
from config import load_config
from mqtt_client import PhoneMqttClient
from sensors import detect_light_sensor, read_light

log = logging.getLogger("phone.main")


class PhoneEdge:
    def __init__(self, config: dict):
        self.config = config
        self.running = True
        self.lux_window = deque(maxlen=3)
        self.sensor_name = config.get("LIGHT_SENSOR_NAME") or detect_light_sensor()
        if self.sensor_name:
            log.info("sensor cahaya terdeteksi: %s", self.sensor_name)
        else:
            log.warning("nama sensor cahaya belum terisi, membaca default sistem")

        self.mqtt = PhoneMqttClient(config)
        self.mqtt.control_handler = self.handle_control

    def handle_control(self, command: str, request_id: str, config_patch: dict | None) -> tuple[bool, str]:
        cmd = str(command).upper()
        if cmd == "START":
            self.running = True
            log.info("perintah START diterima: pemantauan aktif")
            return True, "pemantauan dimulai"
        elif cmd == "STOP":
            self.running = False
            log.info("perintah STOP diterima: pemantauan dijeda")
            return True, "pemantauan dijeda"
        elif cmd == "SET_CONFIG":
            if not config_patch:
                return False, "config patch kosong"
            allowed = ("INTERVAL_S", "LUX_THRESHOLD", "SOUND_THRESHOLD",
                       "CONFIRMATION_WINDOW", "DATA_TIMEOUT_S", "SCHEDULE_START", "SCHEDULE_END")
            for k, v in config_patch.items():
                if k in allowed:
                    self.config[k] = v
            log.info("konfigurasi diperbarui via SET_CONFIG: %s", config_patch)
            return True, "konfigurasi diterapkan"
        else:
            return False, f"perintah tak dikenali: {command}"

    def run_loop(self) -> None:
        self.mqtt.start()
        log.info("loop telemetri HP dimulai (interval=%ds)", int(self.config["INTERVAL_S"]))

        try:
            while True:
                interval = max(3, int(self.config.get("INTERVAL_S", 10)))
                t_start = time.time()

                if self.running:
                    self._step()
                else:
                    log.debug("pemantauan sedang dijeda (status STOP)")

                elapsed = time.time() - t_start
                sleep_time = max(0.5, interval - elapsed)
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            log.info("menghentikan loop HP...")
        finally:
            self.mqtt.stop()

    def _step(self) -> None:
        # 1. Baca cahaya
        lux, valid_light = read_light(self.sensor_name)
        lux_smooth = None
        if valid_light and lux is not None:
            self.lux_window.append(lux)
            lux_smooth = round(sum(self.lux_window) / len(self.lux_window), 2)

        # 2. Baca audio RMS
        sound_rms, valid_audio = measure_sound_level_relative(duration_s=3)

        # 3. Rakit JSON sesuai PRD 5.4 dan spec bagian 4
        payload = {
            "device_id": self.config["DEVICE_ID"],
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "lux": lux,
            "lux_smooth": lux_smooth,
            "sound_level_relative": sound_rms,
            "valid_light": valid_light,
            "valid_audio": valid_audio,
            "simulation_mode": False,
        }

        sent = self.mqtt.send_telemetry(payload)
        log.info("telemetri: lux=%s (smooth=%s) sound=%s sent=%s",
                 lux, lux_smooth, sound_rms, sent)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="LeaveLight Phone Edge (Termux)")
    parser.add_argument("--env", default=".env")
    args = parser.parse_args()

    config = load_config(args.env)
    edge = PhoneEdge(config)
    edge.run_loop()


if __name__ == "__main__":
    main()
