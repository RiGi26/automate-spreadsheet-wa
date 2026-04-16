# Fonnte → Google Sheets (Python)

Webhook server Python yang menangkap pesan jadwal dari WA grup via Fonnte,
lalu menyimpannya ke Google Sheets secara otomatis.

## Alur Kerja

```
WA Grup → Fonnte → Webhook (Python/Flask) → Google Sheets
```

---

## Setup Langkah-langkah

### 1. Buat Google Service Account

1. Buka [console.cloud.google.com](https://console.cloud.google.com)
2. Buat project baru (atau pakai yang ada)
3. Aktifkan dua API:
   - **Google Sheets API**
   - **Google Drive API**
4. Buka **IAM & Admin → Service Accounts → Create Service Account**
5. Isi nama, klik Create
6. Di bagian Keys → Add Key → JSON → Download file JSON-nya
7. Rename file jadi `service_account.json`
8. Taruh di folder `credentials/`

### 2. Share Spreadsheet ke Service Account

1. Buka file `service_account.json`, copy nilai `client_email`
   (format: `xxx@xxx.iam.gserviceaccount.com`)
2. Buka Google Spreadsheet kamu
3. Klik Share → paste email service account → beri akses **Editor**

### 3. Isi File .env

```bash
cp .env.example .env
```

Edit `.env`:
```
SPREADSHEET_ID=ambil_dari_URL_spreadsheet
SHEET_NAME=Jadwal
GOOGLE_CREDS_JSON=credentials/service_account.json
PORT=5000
```

**Cara ambil SPREADSHEET_ID:**
URL spreadsheet: `https://docs.google.com/spreadsheets/d/XXXXXXX/edit`
ID-nya adalah bagian `XXXXXXX`.

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Test Lokal

```bash
# Test parser saja (tidak perlu internet)
python test_lokal.py parser

# Test koneksi Google Sheets
python test_lokal.py sheets

# Test full flow
python test_lokal.py full
```

### 6. Jalankan Server Lokal

```bash
python app.py
```

Server jalan di `http://localhost:5000`

Untuk expose ke internet sementara (testing dengan Fonnte):
```bash
# Install ngrok dulu: https://ngrok.com
ngrok http 5000
```
Copy URL ngrok → paste ke webhook Fonnte.

---

## Deploy ke Railway (Produksi)

1. Push kode ke GitHub
2. Buka [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Set environment variables di Railway dashboard:
   - `SPREADSHEET_ID`
   - `SHEET_NAME`
   - `GOOGLE_CREDS_JSON` = isi konten JSON-nya langsung (bukan path)
4. Untuk credentials JSON di Railway, gunakan environment variable:

Edit `sheets_client.py` bagian `_init_client`, ganti:
```python
# Dari file
creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)

# Ke environment variable (untuk Railway)
import json
creds_json = json.loads(os.getenv('GOOGLE_CREDS_JSON'))
creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
```

5. Setelah deploy, Railway memberi URL seperti `https://xxx.railway.app`
6. Set webhook Fonnte ke: `https://xxx.railway.app/webhook`

---

## Struktur File

```
fonnte-sheets/
├── app.py              ← Flask webhook server (entry point)
├── parser_jadwal.py    ← Ekstrak data dari pesan WA
├── sheets_client.py    ← Koneksi Google Sheets
├── test_lokal.py       ← Script test tanpa deploy
├── requirements.txt
├── Procfile            ← Untuk Railway/Render
├── .env.example        ← Template variabel lingkungan
├── .env                ← Konfigurasi aktual (jangan di-commit!)
├── credentials/
│   └── service_account.json   ← File dari Google Console
└── logs/
    └── app.log         ← Log otomatis
```

---

## Format Output di Google Sheets

| Timestamp | Tanggal | Sesi | Jam | No | Nama |
|---|---|---|---|---|---|
| 2026-04-13 08:00:00 | 13/04/2026 | Sesi I | 08:00 | 1 | Grace Zefanya |
| 2026-04-13 08:00:00 | 13/04/2026 | Sesi I | 08:00 | 2 | Nabil Arsyad |

---

## Troubleshooting

**Parser tidak menangkap semua sesi**
→ Jalankan `python test_lokal.py parser` dan cek output

**Google Sheets error 403**
→ Pastikan spreadsheet sudah di-share ke email service account

**Fonnte webhook tidak nyambung**
→ Pastikan server running dan URL webhook benar (harus HTTPS di produksi)

**`isgroup` selalu False**
→ Cek log di `logs/app.log` untuk lihat payload asli dari Fonnte
