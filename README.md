# LeaveLight IoT 💡

Sistem pemantauan ruangan dan konservasi energi pintar berbasis IoT tanpa sensor eksternal (mengubah HP Android menjadi stasiun pengindera cahaya dan level suara relatif).

LeaveLight mendeteksi kondisi **ruangan kosong saat lampu masih menyala setelah jam operasional kantor/kampus berakhir** dan membunyikan status **"PERIKSA RUANGAN"** di dashboard web operator.

---

## 🏛️ Arsitektur Singkat

```
+-------------------------------------------------------------------------+
|                    MQTT BROKER (HIVEMQ TLS 8883)                        |
+-------------------+---------------------------------+-------------------+
                    ^                                 |
   1. Telemetri     |                                 |  2. Kontrol
   (Lux & RMS)      |                                 |  (START/STOP/SET)
                    |                                 v
+-------------------+---------------+ +---------------+-------------------+
|        EDGE 1: HP ANDROID         | |        EDGE 2: LAPTOP             |
|         (Termux + Python)         | |       (Python + Flask)            |
|                                   | |                                   |
| - termux-sensor (Lux)             | | - mqtt_sub: Listener TLS          |
| - Smoothing lokal (window 3)      | | - validate: Validasi skema        |
| - termux-mic-record + ffmpeg      | | - smoothing: Moving average       |
| - Local RMS (Privasi: audio hapus)| | - rule_engine: Mesin 5 status     |
| - mqtt_client: TLS publisher      | | - store: CSV & SQLite             |
+-------------------+---------------+ | - dashboard: Flask Web UI         |
                    |                 +---------------+-------------------+
                    |  3. ACK                         ^
                    +---------------------------------+
```

- **Edge 1 (HP Android / Termux):**
  - Sensor cahaya via `termux-sensor` (Smoothing lokal).
  - Sensor suara via `termux-microphone-record` & `ffmpeg` (Pengukuran RMS relatif lokal).
  - **Privasi terjamin (NFR-01)**: File audio segera dihapus dari disk, **hanya angka numerik yang keluar dari HP**.
  - Mengirim telemetri ke Broker MQTT via TLS.
- **Broker MQTT (HiveMQ):**
  - Mendukung **HiveMQ Public Broker** (gratis tanpa akun) maupun **HiveMQ Cloud Dedicated Cluster**.
- **Edge 2 & Dashboard (Laptop):**
  - Menerima telemetri, validasi skema (FR-03), smoothing sekunder (FR-04).
  - Rule Engine status (FR-06): `STANDBY` &rarr; `PEMANTAUAN` &rarr; `NORMAL` &rarr; `PERIKSA RUANGAN` / `SENSOR/KONEKSI BERMASALAH`.
  - Penyimpanan: Telemetri mentah ke CSV append-only, Event peringatan ke SQLite (FR-08).
  - Dashboard web Flask responsif dengan grafik real-time Chart.js dan kontrol dua arah (FR-09).

---

## ⚙️ 1. Konfigurasi Broker MQTT (`.env`)

Salin template file `.env.example` ke `.env`:
```bash
cp .env.example .env
```

Pilih salah satu metode broker berikut untuk diisi di `.env`:

### Opsi A: Menggunakan Broker Publik Gratis (Tanpa Akun / Demo Cepat)
Sangat praktis untuk pengujian langsung tanpa perlu registrasi:
```env
MQTT_HOST=broker.hivemq.com
MQTT_PORT=8883
MQTT_TLS=true
MQTT_USERNAME=
MQTT_PASSWORD=

# PENTING: Gunakan PROJECT_ID yang unik agar topik data tidak bentrok dengan pengguna lain di dunia!
PROJECT_ID=leavelight_zelphyx_01
DEVICE_ID=leavelight_phone01

INTERVAL_S=10
LUX_THRESHOLD=150
SOUND_THRESHOLD=0.05
CONFIRMATION_WINDOW=3
DATA_TIMEOUT_S=30
SCHEDULE_START=17:30
SCHEDULE_END=22:00
```

### Opsi B: Menggunakan HiveMQ Cloud Dedicated Cluster (Privat & Produksi)
Jika Anda memiliki akun kluster privat di [HiveMQ Cloud](https://www.hivemq.com/cloud/):
```env
HIVEMQ_CLUSTER_URL=your-cluster-id.s1.eu.hivemq.cloud
HIVEMQ_PORT=8883
HIVEMQ_USERNAME=username_kluster_anda
HIVEMQ_PASSWORD=password_kluster_anda

PROJECT_ID=projek1
DEVICE_ID=leavelight_phone01
```

---

## 💻 2. Panduan Sisi Laptop (Edge 2 & Dashboard)

### A. Kebutuhan Sistem
- Python 3.10+
- Browser modern (Chrome, Edge, Safari, Firefox)

### B. Instalasi Dependensi
```bash
pip install -r requirements-laptop.txt
```
*(Atau gunakan virtual environment: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-laptop.txt`)*

### C. Menjalankan Unit Test (Pytest)
Pastikan semua fungsi murni validasi, smoothing, dan rule engine lolos:
```bash
pytest tests/
```

### D. Menjalankan Pipeline & Dashboard
```bash
python3 laptop/main.py
```
- Dashboard akan otomatis terbuka di browser pada:
  👉 **`http://localhost:5001`** *(atau port 5000 jika tidak bentrok dengan AirPlay)*.
- **Catatan macOS**: Jika port 5000 sedang digunakan oleh macOS AirPlay Receiver, script akan **otomatis beralih ke port 5001** tanpa error.

### E. Fitur-Fitur di Dashboard Web
1. **Status Ruangan Terkini**:
   - `NORMAL`: Ruangan dalam kondisi wajar.
   - `PERIKSA RUANGAN`: **Alert visual menyala/berkedip (amber-merah)** ketika ruangan terang namun sepi suara pasca jam operasional selama durasi konfirmasi berturut-turut.
   - `PEMANTAUAN`: Jam kerja sedang berlangsung (tanpa alert).
   - `STANDBY`: Di luar jam pemantauan.
   - `SENSOR/KONEKSI BERMASALAH`: Data invalid / HP tidak mengirim data melampaui `DATA_TIMEOUT_S`.
2. **Kartu Statistik Live**:
   - Sensor Cahaya: Lux mentah & smoothed lux.
   - Level Suara Relatif: Nilai RMS ternormalisasi (bukan dB).
   - Kesegaran Data: Penghitung detik sejak data terakhir diterima (*fresh/stale badge*).
3. **Grafik Real-Time Chart.js & Fallback**:
   - Visualisasi grafik deret waktu real-time dua sumbu (Lux vs Suara).
   - Dilengkapi tombol *"Tampilkan Tabel Fallback"* jika ingin melihat angka mentah atau jika offline.
4. **Riwayat Event & Aksi Pemeriksaan**:
   - Daftar event `PERIKSA RUANGAN` yang pernah terpicu.
   - Tombol **"Tandai Selesai"** bagi petugas/operator yang telah memeriksa ruangan fisik.
5. **Kontrol Jarak Jauh (Two-Way Control)**:
   - Tombol **START** & **STOP** untuk mengendalikan pemantauan di HP via MQTT.
   - Form **Simpan Konfigurasi** untuk mengubah ambang lux, ambang suara, interval publish, dan jadwal ruangan langsung dari web.

### F. Uji Coba Cepat Tanpa HP Fisik (Simulator)
Jika HP fisik belum terpasang dan Anda ingin menguji dashboard dengan data simulasi:
```bash
# Jalankan di terminal baru:
python3 laptop/simulator.py --scenario alert
```
Pilihan skenario simulator:
- `--scenario normal`: Data wajar dalam jam operasional.
- `--scenario alert`: Data terang + hening pasca jam operasional (memicu `PERIKSA RUANGAN`).
- `--scenario spike`: Satu lonjakan singkat (menguji filter anti-false alarm TC-05).
- `--scenario stale`: Data dengan timestamp basi 5 menit lampau (menguji TC-08).

---

## 📱 3. Panduan Sisi HP Android (Edge 1 via Termux)

### A. Kebutuhan di HP
1. **Aplikasi Termux**: Unduh dari [F-Droid (Termux)](https://f-droid.org/en/packages/com.termux/). *(Jangan dari Play Store!)*
2. **Aplikasi Termux:API**: Unduh dari [F-Droid (Termux:API)](https://f-droid.org/en/packages/com.termux.api/).
3. **Izin Android**:
   - Buka **Pengaturan HP** &rarr; **Aplikasi** &rarr; **Termux:API** &rarr; **Izin**.
   - Berikan izin **Mikrofon** dan **Sensors (Sensor Fisik)**.

### B. Setup Lingkungan di Terminal Termux
Buka aplikasi Termux di HP, lalu jalankan perintah berikut:
```bash
pkg update && pkg upgrade -y
pkg install -y python ffmpeg termux-api git
pip install paho-mqtt numpy
```

### C. Salin File Proyek ke HP
Salin folder [`phone/`](phone/) dan file [`.env`](.env) ke penyimpanan HP:
- Pastikan nilai `MQTT_HOST`, `MQTT_PORT`, dan `PROJECT_ID` di file `.env` HP **sama persis** dengan yang ada di laptop.

### D. Tahap 1: Validasi Perangkat (TC-01, TC-02, TC-03)
Sebelum menyambungkan ke cloud, jalankan skrip diagnostik di HP untuk memastikan sensor terbaca:
```bash
python phone/validate_device.py
```
Skrip ini akan memeriksa:
- Ketersediaan sensor cahaya (`termux-sensor -l`)
- Perekaman audio 2 detik via Termux:API
- Decode WAV via ffmpeg & kalkulasi RMS
- Memastikan 0 file rekaman tersisa di disk (*Zero Audio Leakage*).

### E. Tahap 2: Jalankan Pemantauan Rutin
```bash
python phone/main.py
```
HP akan mulai membaca sensor secara berkala (default tiap 10 detik), melakukan smoothing lux lokal, menghitung RMS audio, dan mengirim telemetri ke broker. Status di dashboard laptop akan otomatis berubah menjadi aktif!

---

## 🧪 4. Matriks Pengujian & Verifikasi (TC-01 s/d TC-10)

| ID Uji | Pengujian | Kriteria Lolos | Status |
|---|---|---|---|
| **TC-01** | Sensor Cahaya HP | Membaca lux numerik wajar (0 - 200.000 lx) | **PASSED** |
| **TC-02** | Rekam & Decode Audio | Mampu merekam 3s & decode WAV via ffmpeg | **PASSED** |
| **TC-03** | Privasi & RMS Audio | Menghasilkan nilai RMS numerik; file sementara terhapus 100% | **PASSED** |
| **TC-04** | Validasi Telemetri | Menolak pesan kosong, field hilang, dan timestamp tanpa zona waktu | **PASSED** |
| **TC-05** | Filter Lonjakan Tunggal | Satu lonjakan terang tidak memicu event sebelum memenuhi streak | **PASSED** |
| **TC-06** | Payload MQTT Lengkap | Telemetri diterima lengkap via TLS dengan catatan waktu tiba | **PASSED** |
| **TC-07** | Alert Pasca Jam Kerja | Status `PERIKSA RUANGAN` terpicu hanya saat jam kerja lewat dan syarat bertahan | **PASSED** |
| **TC-08** | Data Basi / Timeout | Telemetri terhenti &rarr; status `SENSOR/KONEKSI BERMASALAH` tanpa alert palsu | **PASSED** |
| **TC-09** | Kontrol Dua Arah & ACK | START/STOP/SET_CONFIG diterima HP dan status ACK tampil di dashboard | **PASSED** |
| **TC-10** | Retensi & Visualisasi | Data tersimpan di CSV/SQLite, Chart.js & fallback table responsif | **PASSED** |

---

## 📚 5. Dokumen Terkait
- [Spesifikasi Teknis Lengkap](docs/superpowers/specs/2026-10-29-leavelight-design.md)
- [Diagram Arsitektur & Format Payload](docs/arsitektur.md)
- [Detail Hasil Uji Lapangan](docs/hasil-uji.md)
