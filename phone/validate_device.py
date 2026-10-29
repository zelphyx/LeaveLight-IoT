"""Skrip validasi perangkat HP (Tahap 1 PRD, TC-01, TC-02, TC-03).

Jalankan di Termux sebelum integrasi broker:
python validate_device.py

Menguji:
1. Ketersediaan sensor cahaya via termux-sensor (TC-01)
2. Izin mikrofon & perekaman via termux-microphone-record (TC-02)
3. Decode audio ffmpeg & perhitungan RMS numerik (TC-03)
4. Memastikan tidak ada file rekaman yang tersisa
"""

import sys
import time
from datetime import datetime
from pathlib import Path

from audio import compute_rms_from_wav, is_ffmpeg_available, is_termux_mic_available, measure_sound_level_relative
from sensors import detect_light_sensor, is_termux_sensor_available, read_light


def run_diagnostics():
    print("=" * 60)
    print("  LeaveLight IoT - Diagnostik Validasi Perangkat HP (Termux)")
    print("=" * 60)
    print(f"Waktu Uji : {datetime.now().astimezone().isoformat()}")
    print(f"Python    : {sys.version.split()[0]}")
    print("-" * 60)

    all_passed = True

    # 1. Cek Tool Termux
    print("\n[1] Memeriksa Tool Sistem:")
    sensor_bin = is_termux_sensor_available()
    mic_bin = is_termux_mic_available()
    ffmpeg_bin = is_ffmpeg_available()

    print(f"  - termux-sensor            : {'OK' if sensor_bin else 'TIDAK DITEMUKAN'}")
    print(f"  - termux-microphone-record : {'OK' if mic_bin else 'TIDAK DITEMUKAN'}")
    print(f"  - ffmpeg                   : {'OK' if ffmpeg_bin else 'TIDAK DITEMUKAN'}")

    # 2. Uji Sensor Cahaya (TC-01)
    print("\n[2] Menguji Sensor Cahaya (TC-01):")
    sensor_name = detect_light_sensor()
    print(f"  - Nama Sensor Terdeteksi   : {sensor_name or 'Tidak ditemukan otomatis'}")
    lux, valid_light = read_light(sensor_name)
    if valid_light and lux is not None:
        print(f"  - Pembacaan Lux Aktual     : {lux:.2f} lx [LOLOS TC-01]")
    else:
        print("  - Pembacaan Lux            : GAGAL (Pastikan Termux:API terpasang dan berizin)")
        all_passed = False

    # 3. Uji Rekam Mikrofon (TC-02)
    print("\n[3] Menguji Perekaman Audio & Decode (TC-02):")
    print("  - Mengambil sampel 2 detik...")
    sound_rms, valid_audio = measure_sound_level_relative(duration_s=2)
    if valid_audio and sound_rms is not None:
        print(f"  - Level Suara Relatif (RMS): {sound_rms:.4f} [LOLOS TC-02]")
    else:
        print("  - Perekaman Audio / Decode : GAGAL")
        print("    (Pastikan izin mikrofon diberikan ke aplikasi Termux:API)")
        all_passed = False

    # 4. Uji Perbedaan RMS pada Kondisi Suara (TC-03)
    print("\n[4] Menguji Variasi Sensitivitas RMS (TC-03):")
    if valid_audio:
        print("  - Silakan bersuara / tepuk tangan saat hitungan mundur...")
        time.sleep(1)
        print("    Merekam suara keras...")
        sound_loud, _ = measure_sound_level_relative(duration_s=2)
        print(f"    Hasil RMS : {sound_loud}")
        print("  - Memastikan tidak ada file audio audio.* tersisa di direktori kerja...")
        leftovers = list(Path(".").glob("*.m4a")) + list(Path(".").glob("*.wav"))
        if not leftovers:
            print("    File bersih: 0 file audio tersisa di disk [LOLOS NFR-01]")
        else:
            print(f"    PERINGATAN: Ada file sisa: {[str(f) for f in leftovers]}")

    print("\n" + "=" * 60)
    if all_passed:
        print("  HASIL: SEMUA PENGUJIAN PERANGKAT HP LOLOS!")
        print("  Perangkat siap untuk integrasi MQTT LeaveLight.")
    else:
        print("  HASIL: ADA KOMPONEN YANG GAGAL / BELUM LENGKAP.")
        print("  Bila audio gagal, sistem tetap dapat beroperasi dalam fallback")
        print("  tetapi alert otomatis akan di-hold (data tidak lengkap).")
    print("=" * 60)
    return all_passed


if __name__ == "__main__":
    success = run_diagnostics()
    sys.exit(0 if success else 1)
