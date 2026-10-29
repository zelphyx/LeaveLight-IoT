"""Dashboard Flask lokal untuk LeaveLight (bagian 7 spec).

Endpoint: GET / (halaman), GET /api/status, GET /api/history, GET /api/events,
POST /api/events/<id>/check, POST /api/config, POST /api/control.
"""

from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request


def create_app(pipeline) -> Flask:
    templates = str(Path(__file__).parent / "templates")
    statics = str(Path(__file__).parent / "static")
    app = Flask(__name__, template_folder=templates, static_folder=statics)
    config = pipeline.config

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def api_status():
        return jsonify({
            "latest": pipeline.latest,
            "broker": {
                "connected": pipeline.mqtt.connected if pipeline.mqtt else None,
                "error": pipeline.mqtt.last_connect_error if pipeline.mqtt else "mode tanpa broker",
            },
            "received": pipeline.received_count,
            "invalid": pipeline.invalid_count,
        })

    @app.get("/api/history")
    def api_history():
        limit = request.args.get("limit", default=200, type=int)
        return jsonify(pipeline.store.recent_telemetry(min(limit, 1000)))

    @app.get("/api/events")
    def api_events():
        return jsonify(pipeline.store.recent_events(limit=50))

    @app.post("/api/events/<int:event_id>/check")
    def api_check(event_id: int):
        ok = pipeline.store.mark_checked(event_id, datetime.now().astimezone())
        return (jsonify({"checked": True}), 200) if ok else (jsonify({"checked": False}), 404)

    @app.post("/api/config")
    def api_config():
        """Simpan konfigurasi dan kirim SET_CONFIG via kontrol MQTT (TC-09)."""
        body = request.get_json(force=True) or {}
        allowed = ("INTERVAL_S", "LUX_THRESHOLD", "SOUND_THRESHOLD",
                   "CONFIRMATION_WINDOW", "DATA_TIMEOUT_S", "SCHEDULE_START", "SCHEDULE_END")
        patch = {k: v for k, v in body.items() if k in allowed}
        if not patch:
            return jsonify({"error": "tidak ada field konfigurasi yang valid"}), 400
        try:
            _validate_config_patch(patch)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        config.update(patch)
        pipeline.rules = _rebuild_rules(pipeline.rules, config)

        ack_info: dict = {"sent": False}
        if pipeline.mqtt is not None and pipeline.mqtt.connected:
            from control import build_control
            import json as _json
            message, request_id = build_control("SET_CONFIG", config=patch)
            pipeline.mqtt._client.publish(pipeline.t["control"], _json.dumps(message), qos=1)
            ack_info = {"sent": True, "request_id": request_id}

        return jsonify({"config": {k: config[k] for k in allowed}, "mqtt": ack_info})

    @app.post("/api/control")
    def api_control():
        """Kirim START/STOP ke HP (UC-05, TC-09)."""
        body = request.get_json(force=True) or {}
        command = str(body.get("command", "")).upper()
        if command not in ("START", "STOP"):
            return jsonify({"error": "command harus START atau STOP"}), 400
        if pipeline.mqtt is None or not pipeline.mqtt.connected:
            return jsonify({"error": "broker tidak tersambung"}), 503
        from control import build_control
        import json as _json
        message, request_id = build_control(command)
        pipeline.mqtt._client.publish(pipeline.t["control"], _json.dumps(message), qos=1)
        return jsonify({"sent": True, "command": command, "request_id": request_id})

    @app.get("/api/acks")
    def api_acks():
        return jsonify(pipeline.drain_acks())

    return app


def _validate_config_patch(patch: dict) -> None:
    if "INTERVAL_S" in patch and int(patch["INTERVAL_S"]) < 1:
        raise ValueError("INTERVAL_S minimal 1 detik")
    if "CONFIRMATION_WINDOW" in patch and int(patch["CONFIRMATION_WINDOW"]) < 1:
        raise ValueError("CONFIRMATION_WINDOW minimal 1")
    if "DATA_TIMEOUT_S" in patch and int(patch["DATA_TIMEOUT_S"]) < 1:
        raise ValueError("DATA_TIMEOUT_S minimal 1")
    for key in ("SCHEDULE_START", "SCHEDULE_END"):
        if key in patch:
            hour, sep, minute = str(patch[key]).partition(":")
            if not sep or not hour.isdigit() or not minute.isdigit():
                raise ValueError(f"{key} harus format HH:MM")


def _rebuild_rules(engine, config: dict):
    """Bangun ulang rule engine dengan ambang baru, streak direset agar tidak ada alert basi."""
    from rule_engine import RuleEngine
    fresh = RuleEngine(
        lux_threshold=float(config["LUX_THRESHOLD"]),
        sound_threshold=float(config["SOUND_THRESHOLD"]),
        confirmation_window=int(config["CONFIRMATION_WINDOW"]),
        data_timeout_s=int(config["DATA_TIMEOUT_S"]),
        schedule_start=config["SCHEDULE_START"],
        schedule_end=config["SCHEDULE_END"],
    )
    fresh.status = engine.status
    return fresh
