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
from blast_client import BlastClient

load_dotenv('/home/rigizaf26/automate-spreadsheet-wa/.env')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR  = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, 'app.log'), encoding='utf-8')
    ]
)
log = logging.getLogger(__name__)

app    = Flask(__name__)
sheets = SheetsClient()
absen  = AbsenClient(sheets)

FONNTE_TOKEN  = os.getenv("FONNTE_TOKEN", "")
GRUP_BLAST_ID = os.getenv("GRUP_BLAST_ID", "")
blast = BlastClient(sheets, FONNTE_TOKEN, GRUP_BLAST_ID)

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload  = request.get_json(silent=True) or request.form.to_dict()
        log.info(f"Payload masuk: {payload}")

        message  = str(payload.get('message') or payload.get('pesan') or payload.get('text') or '')
        is_group = payload.get('isgroup') or payload.get('isGroup') or payload.get('is_group') or False
        sender   = payload.get('sender') or payload.get('from') or 'unknown'

        if isinstance(is_group, str):
            is_group = is_group.lower() in ('true', '1', 'yes')

        log.info(f"Sender: {sender} | isGroup: {is_group} | Panjang pesan: {len(message)}")

        if not is_group:
            return jsonify(status='ignored', reason='bukan grup'), 200

        # Filter hanya terima dari grup absensi A dan B
        import os
        grup_absensi = [
            os.getenv('GRUP_ABSENSI_A', '').strip(),
            os.getenv('GRUP_ABSENSI_B', '').strip()
        ]
        if sender not in grup_absensi:
            return jsonify(status='ignored', reason='bukan grup absensi'), 200

        if 'DAFTAR KEHADIRAN ANAK' not in message.upper():
            return jsonify(status='ignored', reason='bukan pesan target'), 200

        rows = parse_jadwal(message)
        log.info(f"Berhasil parse {len(rows)} baris data")

        if not rows:
            return jsonify(status='error', reason='parse gagal - tidak ada data'), 200

        saved = sheets.append_rows(rows)
        log.info(f"Tersimpan {saved} baris ke sheet Jadwal (PENDING - menunggu assign jam 23:00)")

        return jsonify(status='ok', saved=saved, message='data disimpan, assign otomatis jam 23:00'), 200

    except Exception as e:
        log.exception(f"Error tidak terduga: {e}")
        return jsonify(status='error', reason=str(e)), 500

@app.route('/', methods=['GET'])
def health():
    return jsonify(status='running', service='fonnte-sheets-webhook'), 200

if __name__ == '__main__':
    port  = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    log.info(f"Server berjalan di port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)

@app.route('/rebuild-rekap', methods=['POST'])
def rebuild_rekap_endpoint():
    secret = request.headers.get('X-Secret', '')
    if secret != 'rebuild123':
        return jsonify({'status': 'error', 'message': 'unauthorized'}), 401
    try:
        import subprocess
        subprocess.Popen([
            '/home/rigizaf26/automate-spreadsheet-wa/venv/bin/python3',
            '/home/rigizaf26/automate-spreadsheet-wa/rebuild_rekap.py'
        ])
        return jsonify({'status': 'ok', 'message': 'rebuild started'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/process-input', methods=['POST'])
def process_input_endpoint():
    secret = request.headers.get('X-Secret', '')
    if secret != 'rebuild123':
        return jsonify({'status': 'error', 'message': 'unauthorized'}), 401
    try:
        from process_input import process_input_jadwal
        import threading
        threading.Thread(target=process_input_jadwal).start()
        return jsonify({'status': 'ok', 'message': 'processing started'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
