"""Pemrosesan audio lokal HP (FR-02, NFR-01, TC-02, TC-03).

Merekam segmen pendek (3 detik) via termux-microphone-record,
mengonversi ke WAV PCM mono 16-bit via ffmpeg, menghitung RMS numerik relatif,
dan segera menghapus semua file audio sementara.
Privasi terjamin: tidak ada suara, rekaman, atau transkrip yang keluar dari perangkat.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


def is_termux_mic_available() -> bool:
    return shutil.which("termux-microphone-record") is not None


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def compute_rms_from_wav(wav_path: Path | str) -> float:
    """Hitung nilai RMS relatif yang dinormalisasi [0.0, 1.0] dari file WAV PCM 16-bit."""
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw_bytes = wf.readframes(n_frames)

    if sampwidth == 2:
        dtype = np.int16
        max_val = 32768.0
    elif sampwidth == 1:
        dtype = np.uint8
        max_val = 128.0
    else:
        dtype = np.int32
        max_val = 2147483648.0

    samples = np.frombuffer(raw_bytes, dtype=dtype).astype(np.float32)
    if sampwidth == 1:
        samples = samples - 128.0

    if len(samples) == 0:
        return 0.0

    rms = float(np.sqrt(np.mean(samples**2)))
    normalized_rms = rms / max_val
    return round(float(np.clip(normalized_rms, 0.0, 1.0)), 4)


def measure_sound_level_relative(duration_s: int = 3) -> tuple[float | None, bool]:
    """Rekam audio, hitung RMS, hapus file. Kembalikan (sound_level_relative, valid_audio)."""
    if not is_termux_mic_available() or not is_ffmpeg_available():
        log.warning("termux-microphone-record atau ffmpeg tidak tersedia di sistem")
        return None, False

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_record = Path(tmpdir) / "segment.m4a"
        wav_target = Path(tmpdir) / "segment.wav"

        try:
            # Pastikan tidak ada sesi rekaman sebelumnya yang menggantung
            try:
                subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=2)
            except Exception:
                pass

            # 1. Mulai rekam (termux-microphone-record berjalan asinkron di latar)
            cmd_record = [
                "termux-microphone-record",
                "-f", str(raw_record),
                "-l", str(duration_s),
            ]
            subprocess.run(cmd_record, capture_output=True, timeout=duration_s + 4, check=True)

            # Tunggu proses perekaman aktual selesai di latar belakang + buffer flushing
            time.sleep(duration_s + 0.5)

            # Pastikan perintah stop rekaman dikirim agar file MP4/M4A terfinalisasi (header moov ditulis)
            try:
                subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=2)
            except Exception:
                pass

            # Beri jeda sejenak agar OS selesai menulis file ke disk
            time.sleep(0.3)

            if not raw_record.exists() or raw_record.stat().st_size == 0:
                log.warning("rekaman audio kosong atau tidak terbentuk")
                return None, False

            # 2. Decode ffmpeg ke WAV PCM 16kHz mono 16-bit
            cmd_ffmpeg = [
                "ffmpeg", "-y", "-i", str(raw_record),
                "-ar", "16000", "-ac", "1", "-f", "wav",
                str(wav_target),
            ]
            subprocess.run(cmd_ffmpeg, capture_output=True, timeout=5, check=True)

            if not wav_target.exists():
                return None, False

            # 3. Hitung RMS
            rms = compute_rms_from_wav(wav_target)
            return rms, True

        except Exception as exc:
            log.warning("gagal mengukur audio: %s", exc)
            return None, False
        finally:
            # Pastikan stop perekaman bila masih berjalan di latar
            try:
                subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=2)
            except Exception:
                pass
            # File dihapus otomatis oleh TemporaryDirectory context manager
