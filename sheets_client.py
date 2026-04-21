"""
sheets_client.py — Koneksi dan operasi ke Google Sheets via gspread
"""

import os
import json
import logging
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

log = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Header tiap sheet
SHEET_HEADERS = {
    'Jadwal':  ['Timestamp', 'Tanggal', 'Sesi', 'Jam', 'No', 'Nama'],
    'PASIEN':  ['NO', 'NAMA', 'TGL_LAHIR', 'NO_RM', 'NO_BPJS', 'TIPE_PASIEN', 'DIAGNOSA', 'TERAPIS_TERAKHIR', 'TGL_SESI_TERAKHIR'],
    'RIWAYAT': ['TIMESTAMP', 'TANGGAL', 'NAMA', 'NO_RM', 'SESI', 'JAM', 'TERAPIS'],
    'TERAPIS': ['TERAPIS', 'JAM', 'KAPASITAS', 'TIPE'],
    'CUTI':    ['TERAPIS', 'TGL_MULAI', 'TGL_SELESAI', 'KETERANGAN'],
}

# Data default TERAPIS — admin bisa ubah kapasitas langsung di sheet
DEFAULT_TERAPIS = [
    ['A', '09.00', 2, 'senior'],
    ['A', '10.00', 2, 'senior'],
    ['A', '10.30', 2, 'senior'],
    ['A', '11.00', 2, 'senior'],
    ['A', '14.00', 2, 'senior'],
    ['A', '14.30', 2, 'senior'],
    ['A', '15.00', 2, 'senior'],
    ['B', '08.00', 2, 'senior'],
    ['B', '08.30', 2, 'senior'],
    ['B', '09.00', 2, 'senior'],
    ['B', '10.00', 2, 'senior'],
    ['B', '10.30', 2, 'senior'],
    ['B', '11.00', 2, 'senior'],
    ['B', '14.00', 2, 'senior'],
    ['B', '14.30', 2, 'senior'],
    ['B', '15.00', 2, 'senior'],
    ['C', '08.00', 3, 'senior'],
    ['C', '08.30', 3, 'senior'],
    ['C', '09.00', 3, 'senior'],
    ['C', '10.00', 3, 'senior'],
    ['C', '10.30', 3, 'senior'],
    ['C', '11.00', 3, 'senior'],
    ['C', '14.00', 3, 'senior'],
    ['C', '14.30', 3, 'senior'],
    ['C', '15.00', 3, 'senior'],
    ['D', '08.00', 1, 'bantu'],
    ['D', '08.30', 1, 'bantu'],
]


class SheetsClient:
    def __init__(self):
        self._client     = None
        self._sheet      = None
        self._worksheets = {}
        self._init_client()

    def _init_client(self):
        try:
            spreadsheet_id = os.getenv('SPREADSHEET_ID')
            if not spreadsheet_id:
                raise ValueError("SPREADSHEET_ID belum diset di .env")

            creds_json = os.getenv('GOOGLE_CREDS_JSON_CONTENT')
            if creds_json:
                log.info("Menggunakan credentials dari environment variable")
                creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)
            else:
                creds_path = os.getenv('GOOGLE_CREDS_JSON', 'credentials/service_account.json')
                log.info(f"Menggunakan credentials dari file: {creds_path}")
                creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)

            self._client = gspread.authorize(creds)
            self._sheet  = self._client.open_by_key(spreadsheet_id)
            log.info(f"Terhubung ke spreadsheet: {spreadsheet_id}")

            self.setup_all_sheets()

        except Exception as e:
            log.error(f"Gagal inisialisasi Google Sheets: {e}")
            raise

    def setup_all_sheets(self):
        """Buat semua sheet yang dibutuhkan jika belum ada."""
        for name, header in SHEET_HEADERS.items():
            ws = self._get_or_create_worksheet(name, header)
            self._worksheets[name] = ws

            if name == 'TERAPIS' and len(ws.get_all_records()) == 0:
                ws.append_rows(DEFAULT_TERAPIS, value_input_option='USER_ENTERED')
                log.info("Sheet TERAPIS diisi data default — sesuaikan kapasitas di sheet")

        log.info("Semua sheet siap")

    def _get_or_create_worksheet(self, name: str, header: list) -> gspread.Worksheet:
        try:
            ws = self._sheet.worksheet(name)
            log.info(f"Worksheet '{name}' ditemukan")
            return ws
        except gspread.WorksheetNotFound:
            log.info(f"Worksheet '{name}' tidak ada, membuat baru...")
            ws = self._sheet.add_worksheet(title=name, rows=1000, cols=20)
            ws.append_row(header)
            log.info(f"Worksheet '{name}' berhasil dibuat")
            return ws

    def get_worksheet(self, name: str) -> gspread.Worksheet:
        if name not in self._worksheets:
            header = SHEET_HEADERS.get(name, [])
            self._worksheets[name] = self._get_or_create_worksheet(name, header)
        return self._worksheets[name]

    def append_rows(self, rows: list[dict]) -> int:
        """Simpan hasil parse WA ke sheet Jadwal."""
        if not rows:
            return 0

        try:
            header  = SHEET_HEADERS['Jadwal']
            key_map = {
                'Timestamp': 'timestamp', 'Tanggal': 'tanggal',
                'Sesi': 'sesi', 'Jam': 'jam', 'No': 'no', 'Nama': 'nama'
            }
            data = [[r.get(key_map[h], '') for h in header] for r in rows]

            ws = self.get_worksheet('Jadwal')
            ws.append_rows(data, value_input_option='USER_ENTERED')
            log.info(f"Berhasil menyimpan {len(data)} baris ke sheet Jadwal")
            return len(data)

        except gspread.exceptions.APIError as e:
            log.error(f"Google Sheets API error: {e}")
            log.info("Mencoba reconnect...")
            self._init_client()
            ws = self.get_worksheet('Jadwal')
            ws.append_rows(data, value_input_option='USER_ENTERED')
            return len(data)

        except Exception as e:
            log.error(f"Gagal menyimpan ke sheet Jadwal: {e}")
            raise

    def get_all_records(self) -> list[dict]:
        try:
            return self.get_worksheet('Jadwal').get_all_records()
        except Exception as e:
            log.error(f"Gagal ambil data Jadwal: {e}")
            return []
