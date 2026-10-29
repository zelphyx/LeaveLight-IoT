"""Simulator HP (FR-12, TC-06..TC-10): terbitkan telemetri sintetis, simulation_mode true.

Pemakaian:
  python simulator.py --scenario normal      # ruangan wajar
  python simulator.py --scenario alert       # terang + sepi -> PERIKSA RUANGAN setelah window
  python simulator.py --scenario spike       # satu lonjakan lux (TC-05)
  python simulator.py --scenario invalid     # lux null, valid_light false (TC-04)
  python simulator.py --scenario stale       # timestamp 5 menit lampau (TC-08)
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
_laptop_dir = Path(__file__).resolve().parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
if str(_laptop_dir) not in sys.path:
    sys.path.insert(0, str(_laptop_dir))
for _sp in _repo_root.glob(".venv/lib/python*/site-packages"):
    if str(_sp) not in sys.path:
        sys.path.insert(0, str(_sp))

import paho.mqtt.client as mqtt
from config import topics


def build_message(scenario: str, seq: int, now: datetime) -> dict:
    base = {
        "device_id": "leavelight_phone01",
        "timestamp": now.isoformat(timespec="seconds"),
        "lux": round(random.uniform(100, 140), 1),
        "sound_level_relative": round(random.uniform(0.05, 0.15), 3),
        "valid_light": True,
        "valid_audio": True,
        "simulation_mode": True,
    }
    if scenario == "alert":
        base["lux"] = round(random.uniform(180, 260), 1)
        base["sound_level_relative"] = round(random.uniform(0.005, 0.03), 3)
    elif scenario == "spike":
        if seq == 2:  # hanya satu interval terang di antara kondisi normal
            base["lux"] = 300.0
            base["sound_level_relative"] = 0.01
    elif scenario == "invalid":
        base["lux"] = None
        base["valid_light"] = False
    elif scenario == "stale":
        base["timestamp"] = (now - timedelta(minutes=5)).isoformat(timespec="seconds")
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulator telemetri LeaveLight")
    parser.add_argument("--scenario", default="normal",
                        choices=["normal", "alert", "spike", "invalid", "stale"])
    parser.add_argument("--interval", type=float, default=2.0,
                        help="interval kirim dalam detik (default 2 agar demo cepat)")
    parser.add_argument("--count", type=int, default=10, help="jumlah pesan")
    parser.add_argument("--env", default=".env")
    args = parser.parse_args()

    from config import load_config
    config = load_config(args.env)
    if not config.get("HIVEMQ_CLUSTER_URL"):
        print("Error: HIVEMQ_CLUSTER_URL belum diisi di .env.")
        print("Silakan salin .env.example ke .env dan isi kredensial cluster HiveMQ Anda.")
        return
    t = topics(config)

    import uuid
    import threading

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"leavelight_sim_{uuid.uuid4().hex[:6]}"
    )
    if config.get("HIVEMQ_USERNAME"):
        client.username_pw_set(config["HIVEMQ_USERNAME"], config.get("HIVEMQ_PASSWORD", ""))
    is_tls = str(config.get("MQTT_TLS", "true")).lower() in ("true", "1", "yes")
    if is_tls:
        client.tls_set()

    connected_evt = threading.Event()
    def on_connect(c, ud, flags, rc, prop=None):
        if rc == 0:
            connected_evt.set()
    client.on_connect = on_connect

    try:
        client.connect(config["HIVEMQ_CLUSTER_URL"], config["HIVEMQ_PORT"], keepalive=60)
        client.loop_start()
    except Exception as exc:
        print(f"Gagal menyambung ke broker HiveMQ: {exc}")
        return

    print("Menghubungkan ke broker MQTT...")
    if not connected_evt.wait(timeout=8):
        print("Peringatan: Timeout menunggu konfirmasi sambungan broker.")

    print(f"Mengirim {args.count} pesan skenario '{args.scenario}' "
          f"ke {t['telemetry']} setiap {args.interval}s")
    for seq in range(1, args.count + 1):
        now = datetime.now().astimezone()
        message = build_message(args.scenario, seq, now)
        pub_result = client.publish(t["telemetry"], json.dumps(message), qos=1)
        pub_result.wait_for_publish(timeout=4)
        print(f"  [{seq}/{args.count}] lux={message['lux']} sound={message['sound_level_relative']}")
        if seq < args.count:
            time.sleep(args.interval)

    time.sleep(1)
    client.loop_stop()
    client.disconnect()
    print("Selesai dikirim.")


if __name__ == "__main__":
    main()
