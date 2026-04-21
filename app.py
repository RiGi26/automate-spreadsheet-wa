"""
app.py — Webhook server: Fonnte → Google Sheets
Jalankan: python app.py
"""

import os
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from parser_jadwal import parse_jadwal
from sheets_client import SheetsClient
from absen_client import AbsenClient

# ─── Setup ────────────────────────────────────────────────
load_dotenv()

# Gunakan path absolut agar bisa jalan di mana saja (lokal & server)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR  = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)  # Buat folder logs otomatis jika belum ada

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, 'app.log'), encoding='utf-8')
    ]
)
log = logging.getLogger(__name__)

app = Flask(__name__)
sheets = SheetsClient()
absen = AbsenClient(sheets)

# ─── Webhook Endpoint ──────────────────────────────────────
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # 1. Ambil payload dari Fonnte
        payload = request.get_json(silent=True) or request.form.to_dict()
        log.info(f"Payload masuk: {payload}")

        message  = str(payload.get('message') or payload.get('pesan') or payload.get('text') or '')
        is_group = payload.get('isgroup') or payload.get('isGroup') or payload.get('is_group') or False
        sender   = payload.get('sender') or payload.get('from') or 'unknown'

        # 2. Normalisasi is_group (bisa string atau bool)
        if isinstance(is_group, str):
            is_group = is_group.lower() in ('true', '1', 'yes')

        log.info(f"Sender: {sender} | isGroup: {is_group} | Panjang pesan: {len(message)}")

        # 3. Filter: harus dari grup
        if not is_group:
            return jsonify(status='ignored', reason='bukan grup'), 200

        # 4. Filter: harus pesan jadwal klinik
        if 'DAFTAR KEHADIRAN ANAK' not in message.upper():
            return jsonify(status='ignored', reason='bukan pesan target'), 200

        # 5. Parse jadwal dari pesan WA
        rows = parse_jadwal(message)
        log.info(f"Berhasil parse {len(rows)} baris data")

        if not rows:
            return jsonify(status='error', reason='parse gagal - tidak ada data'), 200

        # 6. Simpan ke Google Sheets (sheet Jadwal)
        saved = sheets.append_rows(rows)
        log.info(f"Tersimpan {saved} baris ke sheet Jadwal")

        # 7. Assignment terapis otomatis
        assigned_rows = absen.process_assignment(rows)
        log.info(f"Assignment selesai untuk {len(assigned_rows)} pasien")

        # 8. Update sheet PASIEN + catat ke RIWAYAT
        absen.update_after_assignment(assigned_rows)

        # 9. Auto-delete riwayat lama (>30 hari)
        absen.hapus_riwayat_lama()

        # Ringkasan assignment untuk response
        summary = [
            {'nama': r['nama'], 'jam': r['jam'], 'terapis': r.get('terapis', '-')}
            for r in assigned_rows
        ]

        return jsonify(status='ok', saved=saved, assignment=summary), 200

    except Exception as e:
        log.exception(f"Error tidak terduga: {e}")
        return jsonify(status='error', reason=str(e)), 500


# ─── Health check ──────────────────────────────────────────
@app.route('/', methods=['GET'])
def health():
    return jsonify(status='running', service='fonnte-sheets-webhook'), 200


# ─── Run ───────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    log.info(f"Server berjalan di port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
