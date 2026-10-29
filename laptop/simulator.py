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
import time
from datetime import datetime, timedelta, timezone

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

    if config.get("HIVEMQ_USERNAME"):
        client.username_pw_set(config["HIVEMQ_USERNAME"], config.get("HIVEMQ_PASSWORD", ""))
    is_tls = str(config.get("MQTT_TLS", "true")).lower() in ("true", "1", "yes")
    if is_tls:
        client.tls_set()
    try:
        client.connect(config["HIVEMQ_CLUSTER_URL"], config["HIVEMQ_PORT"], keepalive=60)
        client.loop_start()
    except Exception as exc:
        print(f"Gagal menyambung ke broker HiveMQ: {exc}")
        return

    print(f"mengirim {args.count} pesan skenario {args.scenario} "
          f"ke {t['telemetry']} setiap {args.interval}s")
    for seq in range(1, args.count + 1):
        now = datetime.now(timezone(timedelta(hours=7)))
        message = build_message(args.scenario, seq, now)
        client.publish(t["telemetry"], json.dumps(message), qos=1)
        print(f"  [{seq}/{args.count}] lux={message['lux']} sound={message['sound_level_relative']}")
        time.sleep(args.interval)

    client.loop_stop()
    client.disconnect()
    print("selesai")


if __name__ == "__main__":
    main()
