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

# Scope yang dibutuhkan
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Header kolom di sheet — urutan ini harus sama dengan appendRow
HEADER = ['Timestamp', 'Tanggal', 'Sesi', 'Jam', 'No', 'Nama']


class SheetsClient:
    def __init__(self):
        self._client    = None
        self._sheet     = None
        self._worksheet = None
        self._init_client()

    def _init_client(self):
        """Inisialisasi koneksi ke Google Sheets."""
        try:
            spreadsheet_id = os.getenv('SPREADSHEET_ID')
            sheet_name    = os.getenv('SHEET_NAME', 'Jadwal')

            if not spreadsheet_id:
                raise ValueError("SPREADSHEET_ID belum diset di .env")

            # Prioritas 1: dari env var JSON string (untuk cloud/Render)
            creds_json = os.getenv('GOOGLE_CREDS_JSON_CONTENT')
            if creds_json:
                log.info("Menggunakan credentials dari environment variable")
                creds_info = json.loads(creds_json)
                creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
            else:
                # Prioritas 2: dari file lokal
                creds_path = os.getenv('GOOGLE_CREDS_JSON', 'credentials/service_account.json')
                log.info(f"Menggunakan credentials dari file: {creds_path}")
                creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)

            self._client    = gspread.authorize(creds)
            self._sheet     = self._client.open_by_key(spreadsheet_id)
            self._worksheet = self._get_or_create_worksheet(sheet_name)

            log.info(f"Terhubung ke spreadsheet: {spreadsheet_id} | sheet: {sheet_name}")

        except Exception as e:
            log.error(f"Gagal inisialisasi Google Sheets: {e}")
            raise

    def _get_or_create_worksheet(self, name: str):
        """Ambil worksheet; buat baru dengan header jika belum ada."""
        try:
            ws = self._sheet.worksheet(name)
            log.info(f"Worksheet '{name}' ditemukan")
            return ws
        except gspread.WorksheetNotFound:
            log.info(f"Worksheet '{name}' tidak ada, membuat baru...")
            ws = self._sheet.add_worksheet(title=name, rows=1000, cols=10)
            ws.append_row(HEADER)
            log.info(f"Worksheet '{name}' berhasil dibuat dengan header")
            return ws

    def append_rows(self, rows: list[dict]) -> int:
        """
        Simpan list dict hasil parse ke Google Sheets.

        Args:
            rows: List dict dengan key: timestamp, tanggal, sesi, jam, no, nama

        Returns:
            Jumlah baris yang berhasil disimpan
        """
        if not rows:
            return 0

        try:
            # Konversi ke list of list sesuai urutan HEADER
            data = [
                [
                    r.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    r.get('tanggal', ''),
                    r.get('sesi', ''),
                    r.get('jam', ''),
                    r.get('no', ''),
                    r.get('nama', '')
                ]
                for r in rows
            ]

            # Batch insert — lebih efisien daripada satu per satu
            self._worksheet.append_rows(data, value_input_option='USER_ENTERED')
            log.info(f"Berhasil menyimpan {len(data)} baris ke sheet")
            return len(data)

        except gspread.exceptions.APIError as e:
            log.error(f"Google Sheets API error: {e}")
            # Coba reconnect sekali
            log.info("Mencoba reconnect...")
            self._init_client()
            self._worksheet.append_rows(data, value_input_option='USER_ENTERED')
            return len(data)

        except Exception as e:
            log.error(f"Gagal menyimpan ke sheet: {e}")
            raise

    def get_all_records(self) -> list[dict]:
        """Ambil semua data dari sheet (untuk keperluan debug)."""
        try:
            return self._worksheet.get_all_records()
        except Exception as e:
            log.error(f"Gagal ambil data: {e}")
            return []
