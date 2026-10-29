"""Penyimpanan (FR-08): telemetri ke CSV append-only, event ke SQLite."""

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

TELEMETRY_COLUMNS = (
    "received_at", "device_id", "timestamp", "lux", "lux_smooth",
    "sound_level_relative", "valid_light", "valid_audio", "simulation_mode",
    "status", "reason",
)


class Store:
    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.data_dir / "telemetry.csv"
        self.db_path = self.data_dir / "events.db"
        self._init_db()
        self._init_csv()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    lux REAL,
                    sound_level_relative REAL,
                    valid_light INTEGER NOT NULL,
                    valid_audio INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    checked INTEGER NOT NULL DEFAULT 0,
                    checked_at TEXT
                )
                """
            )

    def _init_csv(self) -> None:
        if not self.csv_path.exists():
            with open(self.csv_path, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(TELEMETRY_COLUMNS)

    def save_telemetry(self, message: dict, received_at: datetime,
                       lux_smooth: float | None, status: str, reason: str) -> None:
        with open(self.csv_path, "a", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow([
                received_at.isoformat(timespec="seconds"),
                message["device_id"],
                message["timestamp"],
                message["lux"],
                lux_smooth,
                message["sound_level_relative"],
                int(message["valid_light"]),
                int(message["valid_audio"]),
                int(message["simulation_mode"]),
                status,
                reason,
            ])

    def save_event(self, message: dict, created_at: datetime, reason: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (created_at, device_id, lux, sound_level_relative,
                                    valid_light, valid_audio, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at.isoformat(timespec="seconds"),
                    message["device_id"],
                    message["lux"],
                    message["sound_level_relative"],
                    int(message["valid_light"]),
                    int(message["valid_audio"]),
                    reason,
                ),
            )
            return int(cursor.lastrowid)

    def mark_checked(self, event_id: int, checked_at: datetime) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE events SET checked = 1, checked_at = ? WHERE id = ? AND checked = 0",
                (checked_at.isoformat(timespec="seconds"), event_id),
            )
            return cursor.rowcount > 0

    def recent_events(self, limit: int = 50) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_telemetry(self, limit: int = 200) -> list[dict]:
        """Baca ekor telemetri terakhir untuk grafik dashboard."""
        with open(self.csv_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        out = []
        for row in rows[-limit:]:
            out.append({
                "received_at": row["received_at"],
                "timestamp": row["timestamp"],
                "lux": _num(row["lux"]),
                "lux_smooth": _num(row["lux_smooth"]),
                "sound_level_relative": _num(row["sound_level_relative"]),
                "valid_light": row["valid_light"] == "1",
                "valid_audio": row["valid_audio"] == "1",
                "status": row["status"],
            })
        return out

    def last_event_open(self) -> dict | None:
        events = self.recent_events(limit=1)
        return events[0] if events else None


def _num(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
