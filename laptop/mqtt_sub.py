"""Subscriber MQTT laptop (FR-05): TLS, auto-reconnect, callback telemetri dan ack."""

import logging
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

from config import topics

log = logging.getLogger(__name__)


class MqttSub:
    """Bungkus koneksi paho dengan reconnect backoff dan status koneksi untuk dashboard."""

    def __init__(self, config: dict):
        self.config = config
        self.t = topics(config)
        self.connected = False
        self.last_connect_error = ""
        self.acks: list[dict] = []
        self._ack_lock = threading.Lock()
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"leavelight_laptop_{config['DEVICE_ID']}",
        )
        if config.get("HIVEMQ_USERNAME"):
            self._client.username_pw_set(config["HIVEMQ_USERNAME"], config.get("HIVEMQ_PASSWORD", ""))
        is_tls = str(config.get("MQTT_TLS", "true")).lower() in ("true", "1", "yes")
        if is_tls:
            self._client.tls_set()
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self.telemetry_handler = None  # diisi laptop/main.py

    def start(self) -> None:
        self._connect_with_backoff()

    def _connect_with_backoff(self, max_retries: int = 5) -> None:
        if not self.config.get("HIVEMQ_CLUSTER_URL"):
            self.last_connect_error = "HIVEMQ_CLUSTER_URL belum diisi di .env"
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
                self.last_connect_error = str(exc)
                log.warning("koneksi broker gagal (percobaan %d/%d): %s", attempt, max_retries, exc)
                if attempt < max_retries:
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
        log.error("broker tidak terjangkau setelah %d percobaan", max_retries)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.connected = True
            self.last_connect_error = ""
            client.subscribe(self.t["telemetry"], qos=1)
            client.subscribe(self.t["ack"], qos=1)
            log.info("tersambung, subscribe %s dan %s", self.t["telemetry"], self.t["ack"])
        else:
            self.last_connect_error = f"reason_code={reason_code}"

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = False
        log.warning("terputus dari broker: %s", reason_code)

    def _on_message(self, client, userdata, msg):
        received_at = datetime.now().astimezone()
        if msg.topic == self.t["ack"]:
            ack, reason = _try_parse_ack(msg.payload)
            if ack is None:
                log.warning("ack invalid: %s", reason)
                return
            with self._ack_lock:
                self.acks.append({"received_at": received_at.isoformat(timespec="seconds"), **ack})
            return
        if msg.topic == self.t["telemetry"] and self.telemetry_handler:
            try:
                self.telemetry_handler(msg.payload, received_at)
            except Exception:  # handler error tidak boleh mematikan loop MQTT
                log.exception("handler telemetri error")

    def drain_acks(self) -> list[dict]:
        with self._ack_lock:
            out, self.acks = self.acks, []
        return out

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


def _try_parse_ack(payload: bytes):
    from control import parse_ack
    return parse_ack(payload)
