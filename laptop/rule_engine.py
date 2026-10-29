"""Rule engine: mesin status dan pembuatan event PERIKSA RUANGAN (FR-06, 5.2, bagian 8 spec)."""

from datetime import datetime, timedelta

STANDBY = "STANDBY"
PEMANTAUAN = "PEMANTAUAN"
NORMAL = "NORMAL"
PERIKSA_RUANGAN = "PERIKSA RUANGAN"
SENSOR_BERMASALAH = "SENSOR/KONEKSI BERMASALAH"


class RuleEngine:
    """Evaluasi tiap pesan valid: kesegaran -> jadwal -> kondisi gabungan.

    Counter konfirmasi direset setiap ada interval yang gagal, jadi satu
    lonjakan tunggal tidak memicu event (TC-05). Data basi tidak pernah
    menghasilkan alert baru.
    """

    def __init__(self, lux_threshold: float, sound_threshold: float,
                 confirmation_window: int, data_timeout_s: int,
                 schedule_start: str, schedule_end: str):
        self.lux_threshold = lux_threshold
        self.sound_threshold = sound_threshold
        self.confirmation_window = confirmation_window
        self.data_timeout = timedelta(seconds=data_timeout_s)
        self.schedule_start = _parse_hhmm(schedule_start)
        self.schedule_end = _parse_hhmm(schedule_end)
        self.streak = 0
        self.status = STANDBY
        self.last_reason = "belum ada data"

    def evaluate(self, message: dict, now: datetime) -> tuple[str, str, bool]:
        """Kembalikan (status, alasan, buat_event)."""
        age = now - message["timestamp_parsed"]
        if age > self.data_timeout:
            return self._problem(f"data basi, umur {age.total_seconds():.0f}s melebihi {int(self.data_timeout.total_seconds())}s")

        if not message["valid_light"] or not message["valid_audio"]:
            return self._problem(_incomplete_reason(message))

        if not self._after_schedule(now):
            self.status = STANDBY
            self.last_reason = "di luar jam operasional"
            return self.status, self.last_reason, False

        if not self._after_close(now):
            self.status = PEMANTAUAN
            self.last_reason = "jam operasional belum lewat, pemantauan tanpa alert"
            return self.status, self.last_reason, False

        lux = message["lux"]
        sound = message["sound_level_relative"]
        condition = bool(lux > self.lux_threshold and sound < self.sound_threshold)

        if condition:
            self.streak += 1
        else:
            self.streak = 0
            self.status = NORMAL
            self.last_reason = "kondisi gabungan tidak terpenuhi"
            return self.status, self.last_reason, False

        if self.streak >= self.confirmation_window:
            self.status = PERIKSA_RUANGAN
            self.last_reason = (
                f"lux {lux} > {self.lux_threshold} dan suara {sound} < {self.sound_threshold} "
                f"selama {self.streak} interval berturut-turut"
            )
            return self.status, self.last_reason, True

        self.status = NORMAL
        self.last_reason = f"syarat bertahan {self.streak}/{self.confirmation_window} interval"
        return self.status, self.last_reason, False

    def _problem(self, reason: str) -> tuple[str, str, bool]:
        self.streak = 0
        self.status = SENSOR_BERMASALAH
        self.last_reason = reason
        return self.status, reason, False

    def _after_schedule(self, now: datetime) -> bool:
        """True bila waktu evaluasi berada dalam jendela pemantauan atau sesudahnya."""
        return now.time() >= self.schedule_start

    def _after_close(self, now: datetime) -> bool:
        """True bila jam operasional sudah lewat (saat alert relevan)."""
        return now.time() >= self.schedule_end


def _parse_hhmm(value: str):
    from datetime import time as dtime
    hour, _, minute = value.partition(":")
    return dtime(int(hour), int(minute or 0))


def _incomplete_reason(message: dict) -> str:
    missing = []
    if not message["valid_light"]:
        missing.append("cahaya")
    if not message["valid_audio"]:
        missing.append("suara")
    return f"data tidak lengkap (sensor {', '.join(missing)} tidak valid), bukan kondisi normal"
