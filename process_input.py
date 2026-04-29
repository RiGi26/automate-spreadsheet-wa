import sys
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, '/home/rigizaf26/automate-spreadsheet-wa')
from dotenv import load_dotenv
load_dotenv('/home/rigizaf26/automate-spreadsheet-wa/.env')

from sheets_client import SheetsClient
from absen_client import AbsenClient
from blast_client import BlastClient

log = logging.getLogger(__name__)
WITA = timezone(timedelta(hours=8))

def process_input_jadwal():
    try:
        sc    = SheetsClient()
        absen = AbsenClient(sc)
        blast = BlastClient(sc, None, None)

        ws_jadwal = sc.get_worksheet('Jadwal')
        data      = ws_jadwal.get_all_values()

        if len(data) <= 1:
            log.info("Jadwal kosong")
            return

        # Cari tanggal yang punya baris CANCEL → hanya proses tanggal ini
        tanggal_cancel = set()
        for row in data[1:]:
            while len(row) < 7:
                row.append('')
            status  = str(row[6]).strip().upper()
            tanggal = str(row[1]).strip()
            if status == 'CANCEL' and tanggal:
                tanggal_cancel.add(tanggal)

        # Cari tanggal yang belum pernah diproses sama sekali (semua STATUS kosong)
        tanggal_baru = set()
        tanggal_status = {}  # tanggal -> set of status
        for row in data[1:]:
            while len(row) < 7:
                row.append('')
            status  = str(row[6]).strip().upper()
            tanggal = str(row[1]).strip()
            nama    = str(row[5]).strip()
            if not tanggal or not nama:
                continue
            if tanggal not in tanggal_status:
                tanggal_status[tanggal] = set()
            tanggal_status[tanggal].add(status)

        for tanggal, statuses in tanggal_status.items():
            # Tanggal baru = semua baris statusnya kosong atau PENDING (belum diproses)
            bersih = statuses - {'CANCEL'}
            if bersih == {''} or bersih == set() or bersih == {'PENDING'} or bersih == {'', 'PENDING'}:
                tanggal_baru.add(tanggal)

        # Gabungkan: proses tanggal baru + tanggal yang ada cancel
        tanggal_proses = tanggal_baru | tanggal_cancel

        if not tanggal_proses:
            log.info("Tidak ada tanggal yang perlu diproses")
            return

        log.info(f"Tanggal baru: {tanggal_baru}")
        log.info(f"Tanggal cancel: {tanggal_cancel}")
        log.info(f"Total tanggal diproses: {tanggal_proses}")

        for tanggal in sorted(tanggal_proses):
            _proses_tanggal(sc, absen, blast, ws_jadwal, data, tanggal)

    except Exception as e:
        log.error(f"Error process_input_jadwal: {e}")
        raise


def _proses_tanggal(sc, absen, blast, ws_jadwal, data, tanggal):
    try:
        log.info(f"Proses tanggal: {tanggal}")

        # Hapus RIWAYAT tanggal ini dulu
        _hapus_riwayat_tanggal(sc, tanggal)

        # Ambil semua baris tanggal ini yang bukan CANCEL
        rows_aktif = []

        for i, row in enumerate(data[1:], start=2):
            while len(row) < 7:
                row.append('')

            status  = str(row[6]).strip().upper()
            tgl_row = str(row[1]).strip()
            nama    = str(row[5]).strip()
            sesi    = str(row[2]).strip()
            jam     = str(row[3]).strip().replace('.', ':').replace(' ', '')
            parts = jam.split(':')
            if len(parts) == 2:
                jam = str(int(parts[0])).zfill(2) + ':' + str(int(parts[1])).zfill(2)

            if tgl_row != tanggal:
                continue
            if status == 'CANCEL':
                continue
            if not nama:
                continue

            rows_aktif.append({
                'row_num'  : i,
                'timestamp': datetime.now(WITA).strftime('%d/%m/%Y %H:%M:%S'),
                'tanggal'  : tanggal,
                'sesi'     : sesi,
                'jam'      : jam,
                'nama'     : nama,
            })

        if not rows_aktif:
            log.info(f"Tidak ada pasien aktif di tanggal {tanggal}")
            return

        log.info(f"Assign {len(rows_aktif)} pasien aktif tanggal {tanggal}")

        # Reset STATUS semua baris tanggal ini yang bukan CANCEL
        reset_updates = []
        for i, row in enumerate(data[1:], start=2):
            while len(row) < 7:
                row.append('')
            tgl_row = str(row[1]).strip()
            status  = str(row[6]).strip().upper()
            if tgl_row == tanggal and status != 'CANCEL':
                reset_updates.append({
                    'range': f'G{i}',
                    'values': [['']]
                })
        if reset_updates:
            ws_jadwal.batch_update(reset_updates)

        # Proses assignment
        assigned = absen.process_assignment(rows_aktif)

        # Simpan ke RIWAYAT
        absen.update_after_assignment(assigned)

        # Blast rekap baru
        blast.kirim_rekap(assigned, tanggal)

        # Update STATUS semua baris aktif jadi DONE
        done_updates = []
        for r in rows_aktif:
            done_updates.append({
                'range': f'G{r["row_num"]}',
                'values': [['DONE']]
            })
        ws_jadwal.batch_update(done_updates)

        log.info(f"Selesai tanggal {tanggal}: {len(assigned)} pasien")

    except Exception as e:
        log.error(f"Error _proses_tanggal {tanggal}: {e}")
        raise


def _hapus_riwayat_tanggal(sc, tanggal):
    try:
        ws_riwayat = sc.get_worksheet('RIWAYAT')
        all_vals   = ws_riwayat.get_all_values()
        if len(all_vals) <= 1:
            return

        header    = all_vals[0]
        keep_rows = [header]
        hapus     = 0

        for row in all_vals[1:]:
            tgl_row = str(row[1]).strip() if len(row) > 1 else ''
            if tgl_row == tanggal:
                hapus += 1
            else:
                keep_rows.append(row)

        if hapus > 0:
            ws_riwayat.clear()
            ws_riwayat.append_rows(keep_rows, value_input_option='USER_ENTERED')
            log.info(f"Hapus {hapus} baris RIWAYAT tanggal {tanggal}")

    except Exception as e:
        log.error(f"Error _hapus_riwayat_tanggal: {e}")
        raise


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    process_input_jadwal()
