import sys
import os
import logging
from datetime import datetime
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, '.env'))
from sheets_client import SheetsClient
from rapidfuzz import fuzz, process

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

FUZZY_THRESHOLD = 70

def rebuild_rekap():
    sc = SheetsClient()

    # Ambil FIRST_TERAPIS dari sheet PASIEN (kolom H = index 7)
    ws_pasien    = sc.get_worksheet('PASIEN')
    pasien_vals  = ws_pasien.get_all_values()
    pasien_names = [str(r[1]).strip() for r in pasien_vals[1:] if r[1]]
    pasien_map   = {}
    for r in pasien_vals[1:]:
        nama = str(r[1]).strip()
        if nama:
            pasien_map[nama] = {
                'no_rm'         : str(r[3]).strip(),
                'first_terapis' : str(r[7]).strip() if len(r) > 7 else ''
            }

    # Ambil data RIWAYAT
    ws_riwayat  = sc.get_worksheet('RIWAYAT')
    riwayat_vals = ws_riwayat.get_all_values()
    if len(riwayat_vals) <= 1:
        log.info("RIWAYAT kosong, skip rebuild")
        return

    # Kumpulkan semua tanggal unik → sort
    def parse_date(d):
        try:
            return datetime.strptime(str(d), '%d/%m/%Y')
        except:
            return datetime.min

    tanggal_set = set()
    for row in riwayat_vals[1:]:
        tgl = str(row[1]).strip()
        if tgl:
            tanggal_set.add(tgl)
    tanggal_list = sorted(tanggal_set, key=parse_date)

    # Kelompokkan RIWAYAT per pasien per tanggal
    # pasien_data[nama][tanggal] = terapis
    pasien_data  = {}
    pasien_no_rm = {}

    for row in riwayat_vals[1:]:
        if not any(row):
            continue
        tgl     = str(row[1]).strip()
        nama    = str(row[2]).strip()
        no_rm   = str(row[3]).strip()
        terapis = str(row[6]).strip()

        if not nama or not tgl:
            continue

        if nama not in pasien_data:
            pasien_data[nama]  = {}
            pasien_no_rm[nama] = no_rm

        pasien_data[nama][tgl] = terapis

    # Fuzzy match untuk FIRST_TERAPIS
    first_terapis_cache = {}
    for nama in pasien_data:
        match = process.extractOne(nama, pasien_names, scorer=fuzz.token_set_ratio)
        if match and match[1] >= FUZZY_THRESHOLD:
            matched_name = match[0]
            first_terapis_cache[nama] = pasien_map[matched_name]['first_terapis']
            if match[1] < 100:
                log.info(f"Fuzzy match: '{nama}' -> '{matched_name}' ({match[1]}%)")
        else:
            first_terapis_cache[nama] = ''
            log.warning(f"Tidak match: '{nama}'")

    # Hitung total sesi per pasien
    total_sesi = {nama: len(pasien_data[nama]) for nama in pasien_data}

    # Buat header — kolom per tanggal
    header = ['NAMA', 'NO_RM', 'TOTAL_SESI', 'FIRST_TERAPIS']
    for tgl in tanggal_list:
        header.append(f'TGL_{tgl.replace("/", "_")}')
        header.append(f'TERAPIS_{tgl.replace("/", "_")}')

    # Buat rows
    output_rows = [header]
    for nama, tgl_map in pasien_data.items():
        row = [
            nama,
            pasien_no_rm.get(nama, ''),
            total_sesi[nama],
            first_terapis_cache.get(nama, '')
        ]
        for tgl in tanggal_list:
            terapis = tgl_map.get(tgl, '')  # kosong kalau tidak hadir/cancel
            row.append(tgl if terapis else '')
            row.append(terapis)

        output_rows.append(row)

    # Tulis ke sheet REKAP_PASIEN
    ws_rekap = sc.get_worksheet('REKAP_PASIEN')
    ws_rekap.clear()
    ws_rekap.append_rows(output_rows, value_input_option='USER_ENTERED')

    # Format header
    ws_rekap.format('1:1', {
        'backgroundColor': {'red': 0.267, 'green': 0.447, 'blue': 0.769},
        'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True}
    })

    log.info(f"REKAP_PASIEN rebuild selesai: {len(output_rows)-1} pasien, {len(tanggal_list)} tanggal")

if __name__ == '__main__':
    rebuild_rekap()
