"""Klien MQTT HP (phone edge) untuk LeaveLight (FR-05, FR-09).

Menyambung via TLS ke HiveMQ Cloud, mengirim telemetri, menerima kontrol (START/STOP/SET_CONFIG),
dan membalas dengan ack (UC-05).
"""

import json
import logging
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

from config import topics

log = logging.getLogger(__name__)


class PhoneMqttClient:
    def __init__(self, config: dict):
        self.config = config
        self.t = topics(config)
        self.connected = False
        self.control_handler = None  # callable(command, request_id, config_patch) -> (accepted, reason)
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"leavelight_phone_{config['DEVICE_ID']}",
        )
        if config.get("HIVEMQ_USERNAME"):
            self._client.username_pw_set(config["HIVEMQ_USERNAME"], config.get("HIVEMQ_PASSWORD", ""))
        is_tls = str(config.get("MQTT_TLS", "true")).lower() in ("true", "1", "yes")
        if is_tls:
            self._client.tls_set()
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def start(self) -> None:
        self._connect_with_backoff()

    def _connect_with_backoff(self, max_retries: int = 5) -> None:
        if not self.config.get("HIVEMQ_CLUSTER_URL"):
            log.warning("HIVEMQ_CLUSTER_URL belum diisi di .env; koneksi broker dilewati")
            return
        delay = 2
        for attempt in range(1, max_retries + 1):
            try:
                self._client.connect(
                    self.config["HIVEMQ_CLUSTER_URL"], self.config["HIVEMQ_PORT"], keepalive=60
                )
                self._client.loop_start()
                return
            except (OSError, ValueError, Exception) as exc:
                log.warning("koneksi broker gagal (percobaan %d/%d): %s", attempt, max_retries, exc)
                if attempt < max_retries:
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
        log.error("broker tidak terjangkau setelah %d percobaan", max_retries)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.connected = True
            client.subscribe(self.t["control"], qos=1)
            log.info("tersambung ke broker, subscribe topic kontrol: %s", self.t["control"])
        else:
            log.warning("koneksi ditolak broker, reason_code=%s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = False
        log.warning("terputus dari broker: %s", reason_code)

    def _on_message(self, client, userdata, msg):
        if msg.topic != self.t["control"]:
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as exc:
            log.warning("pesan kontrol bukan JSON valid: %s", exc)
            return

        command = payload.get("command")
        request_id = payload.get("request_id", "")
        cfg_patch = payload.get("config")

        accepted = False
        reason = "handler tidak aktif"

        if self.control_handler:
            try:
                accepted, reason = self.control_handler(command, request_id, cfg_patch)
            except Exception as exc:
                accepted = False
                reason = f"error eksekusi: {exc}"

        # Kirim ACK sesuai format spec bagian 4
        self.send_ack(request_id, accepted, reason)

    def send_telemetry(self, data: dict) -> bool:
        if not self.connected:
            return False
        try:
            payload = json.dumps(data)
            res = self._client.publish(self.t["telemetry"], payload, qos=1)
            return res.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as exc:
            log.warning("gagal publish telemetri: %s", exc)
            return False

    def send_ack(self, request_id: str, accepted: bool, reason: str = "") -> None:
        ack_payload = {
            "device_id": self.config["DEVICE_ID"],
            "request_id": request_id,
            "accepted": accepted,
            "reason": reason,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        try:
            self._client.publish(self.t["ack"], json.dumps(ack_payload), qos=1)
            log.info("ACK terkirim untuk req %s: accepted=%s", request_id, accepted)
        except Exception as exc:
            log.warning("gagal kirim ACK: %s", exc)

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
