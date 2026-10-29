# Desain Teknis LeaveLight MVP

- Tanggal: 2026-10-29
- Status: Disetujui pengguna (berdasarkan PRD v0.1 draft 2026-10-29)
- Ruang lingkup: satu spec untuk seluruh MVP. Phone edge, laptop edge, dan dashboard dibangun dalam satu siklus implementasi.

## 1. Ringkasan

LeaveLight adalah prototipe IoT yang mengubah satu HP Android menjadi sensor cahaya plus pengukur level suara relatif, mengirim hanya metrik numerik via MQTT ke laptop untuk evaluasi aturan, dan menampilkan status plus riwayat PERIKSA RUANGAN di dashboard web lokal. Tidak ada ESP32 atau sensor eksternal. Tidak ada audio yang keluar dari HP.

## 2. Keputusan desain

1. **Broker MQTT: HiveMQ Cloud.** Cluster TLS dengan username dan password dari .env. HP dan laptop tidak harus satu jaringan. Broker publik gratis tidak dipakai kecuali demo darurat.
2. **Penyimpanan: SQLite untuk event, CSV append-only untuk telemetri mentah.** Update status "telah diperiksa" jauh lebih bersih di SQLite. Telemetri CSV gampang dibuka di Excel untuk lampiran laporan.
3. **Pendekatan eksekusi A: bangun full MVP sekaligus.** Script validasi HP (Tahap 1 PRD) tetap dijalankan pertama secara manual di HP sebelum integrasi MQTT. Sisi laptop diuji penuh di sini memakai simulator (FR-12) supaya TC-04 sampai TC-10 lolos tanpa HP fisik.

## 3. Arsitektur dan alur data

HP (Termux, Python) adalah edge 1. Laptop (Python) adalah edge 2. HiveMQ Cloud adalah broker. Dashboard Flask berjalan di laptop dan bisa dibuka dari HP di jaringan yang sama bila perlu.

Loop utama HP setiap interval (default 10 detik):

1. Baca lux via `termux-sensor` memakai nama sensor dari konfigurasi.
2. Rekam segmen audio 3 detik via `termux-microphone-record`, konversi ke wav memakai ffmpeg yang terinstal di Termux, hitung RMS memakai numpy, hapus file audio.
3. Terapkan median atau moving average pada lux, validasi rentang, bangun JSON telemetri, publish.
4. Cek pesan kontrol masuk, terapkan START/STOP atau SET_CONFIG, kirim ack.

Laptop pada setiap pesan: validasi struktur dan tipe (FR-03) -> cek umur data terhadap DATA_TIMEOUT -> smoothing sekunder (moving average baru) -> rule engine -> simpan -> dashboard menampilkan.

Kontrol mengalir sebaliknya: operator mengubah konfigurasi di dashboard -> laptop publish ke topic kontrol -> HP menerapkan dan mengirim ack -> dashboard menampilkan status penerimaan (TC-09).

## 4. Topik dan payload MQTT

Semua topic diawali `leavelight/<PROJECT_ID>/` dengan PROJECT_ID dari .env (default `projek1`).

| Arah | Topic | Isi |
|---|---|---|
| HP -> laptop | `telemetry` | JSON telemetri, satu pesan per interval |
| Laptop -> HP | `control/<device_id>` | START, STOP, atau SET_CONFIG |
| HP -> laptop | `ack/<device_id>` | Hasil penerapan perintah kontrol |

Contoh telemetri (format sesuai PRD 5.4):

```json
{
  "device_id": "leavelight_phone01",
  "timestamp": "2026-10-29T18:30:00+07:00",
  "lux": 145.0,
  "lux_smooth": 138.5,
  "sound_level_relative": 0.082,
  "valid_light": true,
  "valid_audio": true,
  "simulation_mode": false
}
```

Contoh kontrol:

```json
{
  "command": "SET_CONFIG",
  "request_id": "req-20261029-001",
  "timestamp": "2026-10-29T18:00:00+07:00",
  "config": {
    "interval_s": 10,
    "lux_threshold": 150,
    "sound_threshold": 0.05,
    "confirmation_window": 3,
    "schedule_start": "17:30",
    "schedule_end": "22:00"
  }
}
```

Contoh ack:

```json
{
  "device_id": "leavelight_phone01",
  "request_id": "req-20261029-001",
  "accepted": true,
  "reason": "",
  "timestamp": "2026-10-29T18:00:05+07:00"
}
```

Timestamp selalu ISO 8601 dengan zona waktu (+07:00). Laptop menolak pesan tanpa timestamp atau dengan format yang tidak bisa diparse.

## 5. Komponen HP (phone/)

| File | Tugas | Catatan PRD |
|---|---|---|
| `config.py` | Baca .env dan nama sensor, ambang, jadwal, interval | NFR-05, nama sensor beda antar HP |
| `sensors.py` | Jalankan `termux-sensor -l` sekali, baca lux per interval, validasi rentang | FR-01 |
| `audio.py` | Rekam 3 detik, ffmpeg ke wav, hitung RMS, hapus file | FR-02, NFR-01, hanya angka yang keluar |
| `mqtt_client.py` | Paho dengan TLS, publish telemetri, subscribe kontrol, publish ack, reconnect dengan backoff | FR-05, FR-09 |
| `main.py` | Loop interval, smoothing lokal, rakit JSON, tangani START/STOP | FR-04, 2.2 |
| `validate_device.py` | Tahap 1: bukti sensor tersedia, test rekam, test decode, cetak laporan | TC-01, TC-02, TC-03 |

Strategi fallback audio: jika `termux-microphone-record` atau decode gagal di HP target, `audio.py` menetapkan `valid_audio = false` dan loop tetap publish telemetri cahaya. Kegagalan ini dilaporkan oleh validate_device.py sebelum integrasi cloud, sesuai catatan halaman 1 PRD.

Kalau fitur suara tidak tersedia sama sekali, rule engine di laptop memperlakukan pesan dengan `valid_audio = false` sebagai data tidak lengkap (bukan kondisi normal), sehingga tidak ada alert palsu.

## 6. Komponen laptop (laptop/)

| File | Tugas | Catatan PRD |
|---|---|---|
| `mqtt_sub.py` | Subscribe telemetri dan ack, TLS, auto-reconnect, catat waktu terima | FR-05 |
| `validate.py` | Tolak pesan kosong, field hilang, nonnumerik, timestamp invalid | FR-03, TC-04 |
| `smoothing.py` | Moving average atas lux_smooth dari HP, windowing untuk grafik | FR-04, TC-05 |
| `rule_engine.py` | Mesin status dan pembuatan event PERIKSA RUANGAN | FR-06, 5.2 |
| `store.py` | Tulis telemetri ke CSV, event ke SQLite, update status pemeriksaan | FR-08 |
| `control.py` | Publish START/STOP/SET_CONFIG dari dashboard | FR-09 |
| `simulator.py` | Terbitkan telemetri sintetis dengan `simulation_mode: true` | FR-12, TC-06 sampai TC-10 |

## 7. Dashboard (dashboard/)

Flask app lokal, satu halaman utama dengan Chart.js dari CDN (dengan tampilan tabel angka sebagai fallback bila CDN tidak terjangkau).

| Area | Konten | Aksi |
|---|---|---|
| Ringkasan status | Status sistem, lux terakhir, level suara relatif, umur data | Lihat kondisi terbaru |
| Grafik | Deret waktu lux dan sound_level_relative | Pilih rentang waktu bila tersedia |
| Event dan riwayat | Waktu alert, metrik saat event, validitas, catatan | Tandai telah diperiksa |
| Konfigurasi | Jadwal, ambang, durasi konfirmasi, status sensor | Simpan, kirim via kontrol MQTT |
| Koneksi | Status HP, broker, umur pesan terakhir | Lihat error, ulangi koneksi |

Endpoint: `GET /` (halaman), `GET /api/status` (JSON status terbaru), `GET /api/history` (JSON deret waktu), `GET /api/events` (JSON daftar event), `POST /api/events/<id>/check` (tandai diperiksa), `POST /api/config` (simpan dan publish SET_CONFIG), `POST /api/control` (START/STOP).

Label suara di dashboard: "level suara relatif", bukan dB, kecuali sudah dikalibrasi dengan alat acuan (peringatan kuning PRD 5.1).

## 8. Rule engine dan status

Urutan evaluasi setiap pesan valid: kesegaran data -> jadwal -> kondisi gabungan.

| Kondisi | Status | Tindakan |
|---|---|---|
| Pesan tidak valid atau umur melebihi DATA_TIMEOUT | SENSOR/KONEKSI BERMASALAH | Jangan simpulkan kondisi ruangan, catat alasan |
| Di luar jam operasional | STANDBY | Tetap catat data bila pemantauan aktif, tidak evaluasi alert |
| Dalam jendela evaluasi tapi jam operasional belum lewat | PEMANTAUAN | Tampilkan pembacaan tanpa alert |
| Setelah jam operasional, lux di atas ambang dan sound di bawah ambang selama CONFIRMATION_WINDOW interval berturut-turut | PERIKSA RUANGAN | Buat event, tampilkan peringatan untuk pemeriksaan manual |
| Selain itu | NORMAL | Teruskan pemantauan |

Counter konfirmasi direset setiap ada interval yang gagal memenuhi syarat gabungan, jadi satu lonjakan tunggal tidak memicu event (TC-05). Data basi tidak pernah menghasilkan alert baru.

## 9. Konfigurasi awal

Semua nilai di .env, dibagikan ke HP dan laptop via file yang sama (isian broker identik), dan bisa diubah dari dashboard lalu dikirim via SET_CONFIG.

| Parameter | Default | Keterangan |
|---|---|---|
| `PROJECT_ID` | projek1 | Segmen topic MQTT |
| `DEVICE_ID` | leavelight_phone01 | Identitas HP |
| `INTERVAL_S` | 10 | Interval publish HP, NFR-03 menargetkan status tampil 5-10 detik setelah data diterima |
| `LUX_THRESHOLD` | 150 | Ambang masih terang, wajib diuji di lokasi, tidak universal |
| `SOUND_THRESHOLD` | 0.05 | Batas level suara relatif untuk aktivitas rendah, ditentukan dari baseline lokasi |
| `CONFIRMATION_WINDOW` | 3 | Jumlah interval berturut-turut sebelum alert |
| `DATA_TIMEOUT_S` | 30 | Umur maksimum telemetri sebelum ditandai stale |
| `SCHEDULE_START/END` | 17:30 / 22:00 | Jam operasional ruangan uji |
| `LIGHT_SENSOR_NAME` | (diisi dari `termux-sensor -l`) | Nama sensor beda antar HP |

Kredensial `HIVEMQ_CLUSTER_URL`, `HIVEMQ_PORT`, `HIVEMQ_USERNAME`, `HIVEMQ_PASSWORD` hanya di .env. File .env.example berisi placeholder tanpa kredensial. .env masuk .gitignore.

## 10. Penanganan error

- HP gagal baca sensor: kirim lux null dengan `valid_light = false`, laptop menampilkan status bermasalah, bukan normal.
- HP gagal rekam atau decode: `valid_audio = false`, audio dilewati, telemetri cahaya tetap dikirim.
- MQTT putus di HP: retry dengan backoff, buffer bacaan terakhir tidak dikirim ganda, timestamp menunjukkan gap.
- Perintah kontrol tak dikenali atau config invalid: ack `accepted: false` berisi alasan, dashboard menampilkan alasan (UC-05).
- Broker unreachable dari laptop: dashboard menampilkan banner koneksi, status terakhir dibekukan dengan label stale, tidak ada alert baru dari data lama.

## 11. Privasi dan keamanan

NFR-01: audio hanya diproses lokal untuk menghitung fitur. Payload MQTT tidak berisi rekaman, transkrip, atau percakapan. File sementara dihapus setiap interval. NFR-02: koneksi broker memakai TLS dengan kredensial, kredensial tidak masuk kode publik atau GitHub.

## 12. Strategi pengujian

Sisi HP memakai `phone/validate_device.py` di perangkat target: TC-01 (satu pembacaan lux numerik plus timestamp), TC-02 (izin mikrofon aktif, berkas terekam dan bisa didecode), TC-03 (RMS berbeda pada kondisi suara berbeda, tidak ada audio di payload).

Sisi laptop memakai `laptop/simulator.py` plus unit test pytest untuk fungsi murni (validate, smoothing, rule engine): TC-04 (pesan invalid tidak memicu alert), TC-05 (lonjakan tunggal tidak memicu event sebelum window terpenuhi), TC-06 (payload lengkap diterima dengan timestamp), TC-07 (alert hanya saat jadwal aktif dan semua syarat bertahan), TC-08 (data basi tampil bermasalah tanpa alert baru), TC-09 (START/STOP sampai ke HP dan status ack tampil), TC-10 (status, grafik, event tersimpan dan tampil kembali).

Kriteria selesai mengikuti PRD 8.1: kedua sensor diuji di HP target, dua edge menunjukkan dua jenis pemrosesan (HP: lux smoothing plus RMS audio; laptop: smoothing sekunder plus rule engine), seluruh kanal MQTT diuji, payload bebas audio, README, diagram, hasil uji, PPT, dan video demo tersedia. PPT dan video dikerjakan pengguna dari artefak repo.

## 13. Struktur file

```
LeaveLight-IoT/
  phone/
    main.py
    config.py
    sensors.py
    audio.py
    mqtt_client.py
    validate_device.py
  laptop/
    main.py
    mqtt_sub.py
    validate.py
    smoothing.py
    rule_engine.py
    store.py
    control.py
    simulator.py
  dashboard/
    app.py
    templates/index.html
    static/style.css
  tests/
    test_validate.py
    test_smoothing.py
    test_rule_engine.py
  data/                 (dibuat saat runtime, tidak di-commit)
  docs/
    arsitektur.md        (diagram ASCII topik, payload, aliran data)
    hasil-uji.md        (tabel TC-01 sampai TC-10, kolom hasil aktual)
  .env.example
  .gitignore
  requirements-hp.txt
  requirements-laptop.txt
  README.md             (panduan Termux dan HiveMQ langkah demi langkah)
```

## 14. Batasan dan asumsi yang dikonfirmasi

1. Sensor cahaya harus bisa dibaca via Termux:API di HP target. Bila nama sensor tidak standar, diatasi lewat konfigurasi LIGHT_SENSOR_NAME.
2. Izin mikrofon diberikan dan format rekaman bisa didekode oleh ffmpeg di Termux. Bila tidak, metrik suara dinonaktifkan dan aturan cahaya saja tidak cukup memicu alert (butuh valid_audio true).
3. Metrik suara adalah level relatif hasil pemrosesan lokal, bukan dB SPL terkalibrasi.
4. HP dan laptop punya akses internet ke broker HiveMQ Cloud. Dashboard lokal diakses via jaringan yang sama bila dibuka dari HP.
