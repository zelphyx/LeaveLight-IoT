"""Test rule engine sesuai FR-06, Bagian 8, TC-05, TC-07, TC-08 spec LeaveLight."""

from datetime import datetime, timezone, timedelta
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "laptop"))
from rule_engine import RuleEngine, NORMAL, PERIKSA_RUANGAN, PEMANTAUAN, STANDBY, SENSOR_BERMASALAH


def _msg(ts: datetime, lux=200.0, sound=0.02, valid_light=True, valid_audio=True):
    return {
        "device_id": "phone01",
        "timestamp_parsed": ts,
        "lux": lux,
        "sound_level_relative": sound,
        "valid_light": valid_light,
        "valid_audio": valid_audio,
        "simulation_mode": False,
    }


def test_standby_outside_schedule():
    # Jam 12:00 di luar jadwal 17:30 - 22:00
    engine = RuleEngine(150.0, 0.05, confirmation_window=3, data_timeout_s=30,
                        schedule_start="17:30", schedule_end="22:00")
    now = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
    status, reason, alert = engine.evaluate(_msg(now), now)
    assert status == STANDBY
    assert alert is False


def test_monitoring_during_schedule():
    # Jam 19:00: setelah 17:30 tapi sebelum 22:00
    engine = RuleEngine(150.0, 0.05, confirmation_window=3, data_timeout_s=30,
                        schedule_start="17:30", schedule_end="22:00")
    now = datetime(2026, 10, 29, 19, 0, 0, tzinfo=timezone.utc)
    status, reason, alert = engine.evaluate(_msg(now, lux=300.0, sound=0.01), now)
    assert status == PEMANTAUAN
    assert alert is False


def test_single_spike_does_not_trigger_alert_tc05():
    # Jam 22:30: pasca jadwal
    engine = RuleEngine(150.0, 0.05, confirmation_window=3, data_timeout_s=30,
                        schedule_start="17:30", schedule_end="22:00")
    t0 = datetime(2026, 10, 29, 22, 30, 0, tzinfo=timezone.utc)
    
    # Interval 1: lux tinggi sound rendah (streak = 1) -> belum alert
    status, reason, alert = engine.evaluate(_msg(t0, lux=200.0, sound=0.02), t0)
    assert status == NORMAL
    assert alert is False
    assert engine.streak == 1

    # Interval 2: sound naik -> streak reset ke 0
    t1 = t0 + timedelta(seconds=10)
    status, reason, alert = engine.evaluate(_msg(t1, lux=200.0, sound=0.10), t1)
    assert status == NORMAL
    assert alert is False
    assert engine.streak == 0


def test_confirmation_window_triggers_periksa_ruangan_tc07():
    # Pasca jam operasional, kondisi bertahan selama 3 interval berturut-turut
    engine = RuleEngine(150.0, 0.05, confirmation_window=3, data_timeout_s=30,
                        schedule_start="17:30", schedule_end="22:00")
    base = datetime(2026, 10, 29, 22, 30, 0, tzinfo=timezone.utc)

    # Interval 1: streak 1
    _, _, a1 = engine.evaluate(_msg(base, 200.0, 0.02), base)
    assert not a1
    assert engine.streak == 1

    # Interval 2: streak 2
    t1 = base + timedelta(seconds=10)
    _, _, a2 = engine.evaluate(_msg(t1, 200.0, 0.02), t1)
    assert not a2
    assert engine.streak == 2

    # Interval 3: streak 3 -> ALERT PERIKSA RUANGAN
    t2 = base + timedelta(seconds=20)
    status, reason, a3 = engine.evaluate(_msg(t2, 200.0, 0.02), t2)
    assert a3 is True
    assert status == PERIKSA_RUANGAN
    assert engine.streak == 3


def test_stale_data_reports_problem_without_alert_tc08():
    engine = RuleEngine(150.0, 0.05, confirmation_window=3, data_timeout_s=30,
                        schedule_start="17:30", schedule_end="22:00")
    t_msg = datetime(2026, 10, 29, 22, 30, 0, tzinfo=timezone.utc)
    t_now = t_msg + timedelta(seconds=45)  # 45 detik lewat batas timeout 30s

    status, reason, alert = engine.evaluate(_msg(t_msg, 250.0, 0.01), t_now)
    assert status == SENSOR_BERMASALAH
    assert alert is False
    assert "data basi" in reason
    assert engine.streak == 0


def test_invalid_sensor_flag_reports_problem():
    engine = RuleEngine(150.0, 0.05, confirmation_window=3, data_timeout_s=30,
                        schedule_start="17:30", schedule_end="22:00")
    now = datetime(2026, 10, 29, 22, 30, 0, tzinfo=timezone.utc)
    # Suara gagal di HP (valid_audio: false)
    status, reason, alert = engine.evaluate(_msg(now, valid_audio=False), now)
    assert status == SENSOR_BERMASALAH
    assert alert is False
    assert "data tidak lengkap" in reason
