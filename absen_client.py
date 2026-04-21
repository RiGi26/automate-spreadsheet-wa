"""
absen_client.py — Logic assignment terapis otomatis
Alur: parse WA → cocokkan pasien → assign terapis → catat riwayat
"""

import random
import logging
from datetime import datetime, timedelta
from rapidfuzz import fuzz, process

log = logging.getLogger(__name__)

# Threshold fuzzy match nama pasien (0-100)
FUZZY_THRESHOLD = 70

# Hari auto-delete riwayat lama
RIWAYAT_RETENTION_DAYS = 30


class AbsenClient:
    def __init__(self, sheets_client):
        self.sheets = sheets_client

    # ─── Entry Point ──────────────────────────────────────────

    def process_assignment(self, rows: list[dict]) -> list[dict]:
        """
        Dipanggil setelah parse_jadwal().
        Input : list of {timestamp, tanggal, sesi, jam, no, nama}
        Output: list yang sama + field 'terapis' dan 'no_rm'
        """
        if not rows:
            return rows

        tanggal = rows[0]['tanggal']

        # Kelompokkan pasien per jam sesi
        jam_groups: dict[str, list] = {}
        for row in rows:
            jam_groups.setdefault(row['jam'], []).append(row)

        results = []
        for jam, pasien_list in jam_groups.items():
            assigned = self._assign_per_jam(pasien_list, jam, tanggal)
            results.extend(assigned)

        return results

    # ─── Assignment Logic ─────────────────────────────────────

    def _assign_per_jam(self, pasien_list: list, jam: str, tanggal: str) -> list:
        """Assign terapis untuk semua pasien di satu jam sesi."""

        # 1. Terapis yang available (sudah filter cuti)
        available = self._get_available_terapis(jam, tanggal)
        if not available:
            log.warning(f"Tidak ada terapis available jam {jam} tgl {tanggal}")
            for p in pasien_list:
                p['terapis'] = 'MANUAL'
                p['catatan'] = 'Tidak ada terapis tersedia — assign manual'
            return pasien_list

        # 2. Baca terapis_terakhir tiap pasien
        for p in pasien_list:
            data = self._get_pasien_data(p['nama'])
            p['terapis_terakhir'] = data.get('TERAPIS_TERAKHIR', '') if data else ''
            p['no_rm'] = data.get('NO_RM', '') if data else ''

        # 3. Track kapasitas terpakai per terapis
        cap_used: dict[str, int] = {t['terapis']: 0 for t in available}

        # 4. Assign satu per satu
        for p in pasien_list:
            terakhir = p.get('terapis_terakhir', '')
            assigned = self._pick_terapis(available, cap_used, terakhir)
            p['terapis'] = assigned
            if assigned != 'MANUAL':
                cap_used[assigned] = cap_used.get(assigned, 0) + 1
            log.info(f"  {p['nama']} → Terapis {assigned} (terakhir: {terakhir or '-'})")

        return pasien_list

    def _pick_terapis(self, available: list, cap_used: dict, terakhir: str) -> str:
        """
        Pilih terapis berdasarkan prioritas:
        1. Terapis C (kapasitas terbesar) → diisi duluan
        2. Overflow ke A atau B secara random
        3. D hanya sebagai tenaga bantu (fallback terakhir)
        4. Kalau semua tidak bisa → flag MANUAL
        """
        cap = {t['terapis']: t['kapasitas'] for t in available}
        c_cap = cap.get('C', 0)

        # Prioritas 1: Terapis C
        if 'C' in cap:
            if terakhir != 'C' and cap_used.get('C', 0) < c_cap:
                return 'C'

        # Prioritas 2: A atau B (random, constraint ≤ kapasitas C)
        ab_candidates = [
            t for t in available
            if t['terapis'] in ('A', 'B')
            and t['tipe'] == 'senior'
            and t['terapis'] != terakhir
            and cap_used.get(t['terapis'], 0) < t['kapasitas']
            and cap_used.get(t['terapis'], 0) < c_cap  # kapasitas A/B tidak melebihi C
        ]
        if ab_candidates:
            chosen = random.choice(ab_candidates)
            return chosen['terapis']

        # Prioritas 3: D (tenaga bantu, fallback)
        if 'D' in cap:
            if terakhir != 'D' and cap_used.get('D', 0) < cap['D']:
                return 'D'

        # Edge case: tidak bisa assign otomatis
        log.warning(f"Tidak bisa assign otomatis (terakhir={terakhir}) — flag MANUAL")
        return 'MANUAL'

    # ─── Post-Assignment: Update Sheet ───────────────────────

    def update_after_assignment(self, assigned_rows: list[dict]):
        """
        Setelah assignment selesai:
        1. Update TERAPIS_TERAKHIR di sheet PASIEN
        2. Catat ke sheet RIWAYAT
        """
        try:
            ws_pasien = self.sheets.get_worksheet('PASIEN')
            all_pasien = ws_pasien.get_all_records()
            names = [p['NAMA'] for p in all_pasien]

            riwayat_rows = []
            pasien_updates = []  # batch update untuk efisiensi

            for row in assigned_rows:
                if row.get('terapis') == 'MANUAL':
                    continue

                # Cari baris pasien di sheet PASIEN
                match = process.extractOne(
                    row['nama'], names, scorer=fuzz.token_sort_ratio
                )
                if match and match[1] >= FUZZY_THRESHOLD:
                    idx = names.index(match[0])
                    row_num = idx + 2  # header di baris 1, data mulai baris 2
                    pasien_updates.append({
                        'row': row_num,
                        'terapis': row.get('terapis', ''),
                        'tanggal': row.get('tanggal', '')
                    })
                else:
                    log.warning(f"Pasien '{row['nama']}' tidak match untuk update sheet PASIEN")

                # Siapkan baris riwayat
                riwayat_rows.append([
                    row.get('timestamp', ''),
                    row.get('tanggal', ''),
                    row.get('nama', ''),
                    row.get('no_rm', ''),
                    row.get('sesi', ''),
                    row.get('jam', ''),
                    row.get('terapis', '')
                ])

            # Update PASIEN satu per satu (gspread batch_update bisa ditambah nanti)
            for upd in pasien_updates:
                ws_pasien.update_cell(upd['row'], 8, upd['terapis'])    # kolom TERAPIS_TERAKHIR
                ws_pasien.update_cell(upd['row'], 9, upd['tanggal'])    # kolom TGL_SESI_TERAKHIR
            log.info(f"Update {len(pasien_updates)} pasien di sheet PASIEN")

            # Batch write ke RIWAYAT
            if riwayat_rows:
                ws_riwayat = self.sheets.get_worksheet('RIWAYAT')
                ws_riwayat.append_rows(riwayat_rows, value_input_option='USER_ENTERED')
                log.info(f"Catat {len(riwayat_rows)} baris ke sheet RIWAYAT")

        except Exception as e:
            log.error(f"Error update_after_assignment: {e}")
            raise

    def hapus_riwayat_lama(self, days: int = RIWAYAT_RETENTION_DAYS):
        """Auto-delete riwayat yang lebih dari X hari."""
        try:
            ws = self.sheets.get_worksheet('RIWAYAT')
            all_records = ws.get_all_records()

            cutoff = datetime.now().date() - timedelta(days=days)
            header = ['TIMESTAMP', 'TANGGAL', 'NAMA', 'NO_RM', 'SESI', 'JAM', 'TERAPIS']

            rows_to_keep = []
            deleted = 0

            for r in all_records:
                try:
                    tgl = datetime.strptime(r['TANGGAL'], '%d/%m/%Y').date()
                    if tgl >= cutoff:
                        rows_to_keep.append([r.get(h, '') for h in header])
                    else:
                        deleted += 1
                except Exception:
                    rows_to_keep.append([r.get(h, '') for h in header])

            if deleted > 0:
                ws.clear()
                ws.append_row(header)
                if rows_to_keep:
                    ws.append_rows(rows_to_keep, value_input_option='USER_ENTERED')
                log.info(f"Auto-delete: hapus {deleted} riwayat lama (>{days} hari)")

        except Exception as e:
            log.error(f"Error hapus_riwayat_lama: {e}")

    # ─── Helper: Baca Data ────────────────────────────────────

    def _get_available_terapis(self, jam: str, tanggal: str) -> list[dict]:
        """
        Ambil terapis yang punya slot di jam ini dan tidak sedang cuti.
        Returns: [{'terapis': 'C', 'kapasitas': 3, 'tipe': 'senior'}, ...]
        """
        try:
            ws_terapis = self.sheets.get_worksheet('TERAPIS')
            all_terapis = ws_terapis.get_all_records()

            ws_cuti = self.sheets.get_worksheet('CUTI')
            all_cuti = ws_cuti.get_all_records()

            tgl = datetime.strptime(tanggal, '%d/%m/%Y').date()

            # Kumpulkan siapa yang cuti hari ini
            cuti_hari_ini = set()
            for c in all_cuti:
                try:
                    tgl_mulai = datetime.strptime(c['TGL_MULAI'], '%d/%m/%Y').date()
                    tgl_selesai = datetime.strptime(c['TGL_SELESAI'], '%d/%m/%Y').date()
                    if tgl_mulai <= tgl <= tgl_selesai:
                        cuti_hari_ini.add(str(c['TERAPIS']).upper())
                except Exception:
                    pass

            if cuti_hari_ini:
                log.info(f"Terapis cuti hari ini: {cuti_hari_ini}")

            # Filter: jam cocok + tidak cuti
            available = []
            for t in all_terapis:
                if str(t['JAM']) == str(jam) and str(t['TERAPIS']).upper() not in cuti_hari_ini:
                    available.append({
                        'terapis': str(t['TERAPIS']).upper(),
                        'kapasitas': int(t['KAPASITAS']),
                        'tipe': str(t['TIPE']).lower()
                    })

            log.info(f"Terapis available jam {jam}: {[a['terapis'] for a in available]}")
            return available

        except Exception as e:
            log.error(f"Error _get_available_terapis: {e}")
            return []

    def _get_pasien_data(self, nama: str) -> dict | None:
        """Fuzzy match nama ke sheet PASIEN, return data pasien atau None."""
        try:
            ws = self.sheets.get_worksheet('PASIEN')
            all_pasien = ws.get_all_records()

            if not all_pasien:
                return None

            names = [p['NAMA'] for p in all_pasien]
            match = process.extractOne(nama, names, scorer=fuzz.token_sort_ratio)

            if match and match[1] >= FUZZY_THRESHOLD:
                idx = names.index(match[0])
                log.debug(f"Fuzzy match '{nama}' → '{match[0]}' ({match[1]}%)")
                return all_pasien[idx]

            log.warning(f"Pasien '{nama}' tidak ditemukan (best: {match})")
            return None

        except Exception as e:
            log.error(f"Error _get_pasien_data: {e}")
            return None
