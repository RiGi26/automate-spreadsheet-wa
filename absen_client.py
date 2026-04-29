import random
import logging
from datetime import datetime, timedelta
from rapidfuzz import fuzz, process

log = logging.getLogger(__name__)
FUZZY_THRESHOLD = 70
RIWAYAT_RETENTION_DAYS = 30


class AbsenClient:
    def __init__(self, sheets_client):
        self.sheets = sheets_client

    def process_assignment(self, rows):
        if not rows:
            return rows

        tanggal = rows[0]["tanggal"]

        # Load konfigurasi: quota per terapis per jam + info cuti
        terapis_config, dadakan_map = self._get_terapis_config(tanggal)
        if not terapis_config:
            for r in rows:
                r["terapis"] = "MANUAL"
            return rows

        # Load semua pasien sekali
        all_pasien = self._load_all_pasien()
        for row in rows:
            data = self._match_pasien(row["nama"], all_pasien)
            row["terapis_terakhir"] = data.get("TIPE TERAPIS", "") if data else ""
            row["no_rm"] = data.get("NO_RM", "") if data else ""

        # Kelompokkan per jam
        jam_groups = {}
        for row in rows:
            jam_groups.setdefault(row["jam"], []).append(row)

        # Track quota terpakai per terapis per jam
        # quota_used[jam][terapis] = jumlah pasien
        quota_used = {}
        daily_used = {t: 0 for t in terapis_config}

        results = []
        for jam, pasien_list in jam_groups.items():
            quota_used[jam] = {}

            # Quota per terapis di jam ini
            # Normal: 1 per terapis
            # Dadakan: terapis cover dapat +1
            jam_quota = {}
            for t in terapis_config:
                if jam in terapis_config[t]["jams"]:
                    jam_quota[t] = 1  # default quota 1

            # Tambah quota untuk cover dadakan
            for (t_cuti, j), cover_list in dadakan_map.items():
                if j == jam:
                    for t_cover in cover_list:
                        if t_cover in jam_quota:
                            jam_quota[t_cover] = jam_quota.get(t_cover, 0) + 1
                            log.info("Quota darurat " + t_cover + " di jam " + jam + " = " + str(jam_quota[t_cover]) + " (cover " + t_cuti + ")")

            log.info("Jam " + jam + " quota: " + str(jam_quota))

            for p in pasien_list:
                terakhir = p.get("terapis_terakhir", "")
                assigned = self._pick_terapis(jam_quota, quota_used[jam], daily_used, terakhir)
                p["terapis"] = assigned
                if assigned != "MANUAL":
                    quota_used[jam][assigned] = quota_used[jam].get(assigned, 0) + 1
                    daily_used[assigned] = daily_used.get(assigned, 0) + 1
                log.info("  " + p.get("nama","") + " [jam " + jam + "] -> " + assigned + " (terakhir: " + (terakhir or "-") + ")")

            results.extend(pasien_list)

        log.info("Distribusi harian: " + str(dict(daily_used)))
        return results

    def _pick_terapis(self, jam_quota, jam_used, daily_used, terakhir):
        """
        Pilih terapis berdasarkan:
        1. Masih ada quota di jam ini
        2. Bukan terapis terakhir pasien (rotasi)
        3. Prioritas: C -> A/B random -> D
        """
        def has_quota(t):
            return jam_used.get(t, 0) < jam_quota.get(t, 0)

        def eligible(t):
            return t in jam_quota and has_quota(t) and t != terakhir

        # Prioritas 1: C
        if eligible("C"):
            return "C"

        # Prioritas 2: A atau B random
        ab = [t for t in jam_quota if t in ("A","B") and has_quota(t) and t != terakhir]
        if ab:
            return random.choice(ab)

        # Prioritas 3: D
        if eligible("D"):
            return "D"

        # Override rotasi — abaikan rotasi, pilih yang masih ada quota
        for t in ["C","A","B","D"]:
            if t in jam_quota and has_quota(t):
                log.warning("Override rotasi -> " + t + " (terakhir=" + terakhir + ")")
                return t

        # Override total — pilih yang daily_used paling sedikit (last resort)
        candidates = [t for t in ["C","A","B","D"] if t in jam_quota]
        if candidates:
            t = min(candidates, key=lambda x: daily_used.get(x, 0))
            log.warning("Override total -> " + t + " (quota habis, daily_used=" + str(daily_used) + ")")
            return t

        return "MANUAL"

    def update_after_assignment(self, assigned_rows):
        try:
            riwayat = []
            for row in assigned_rows:
                if row.get("terapis") == "MANUAL":
                    continue
                riwayat.append([
                    row.get("timestamp",""), row.get("tanggal",""),
                    row.get("nama",""), row.get("no_rm",""),
                    row.get("sesi",""), row.get("jam",""),
                    row.get("terapis","")
                ])
            if riwayat:
                self.sheets.get_worksheet("RIWAYAT").append_rows(riwayat, value_input_option="USER_ENTERED")
                log.info("Catat " + str(len(riwayat)) + " baris ke RIWAYAT")
        except Exception as e:
            log.error("Error update_after_assignment: " + str(e))
            raise

    def hapus_riwayat_lama(self, days=RIWAYAT_RETENTION_DAYS):
        try:
            ws = self.sheets.get_worksheet("RIWAYAT")
            all_records = ws.get_all_records()
            cutoff = datetime.now().date() - timedelta(days=days)
            header = ["TIMESTAMP","TANGGAL","NAMA","NO_RM","SESI","JAM","TERAPIS"]
            keep, deleted = [], 0
            for r in all_records:
                try:
                    if datetime.strptime(r["TANGGAL"], "%d/%m/%Y").date() >= cutoff:
                        keep.append([r.get(h,"") for h in header])
                    else:
                        deleted += 1
                except Exception:
                    keep.append([r.get(h,"") for h in header])
            if deleted > 0:
                ws.clear()
                ws.append_row(header)
                if keep:
                    ws.append_rows(keep, value_input_option="USER_ENTERED")
                log.info("Auto-delete: hapus " + str(deleted) + " riwayat lama")
        except Exception as e:
            log.error("Error hapus_riwayat_lama: " + str(e))

    def _get_terapis_config(self, tanggal):
        """
        Return:
          terapis_config = {
            "C": {"jams": {"08:00","08:30",...}, "tipe": "senior"},
            ...
          }
          dadakan_map = {
            ("A", "09:00"): ["C"],  # A dadakan jam 09:00, C yang cover
            ...
          }
        """
        try:
            all_terapis = self.sheets.get_worksheet("TERAPIS").get_all_records()
            all_cuti = self.sheets.get_worksheet("CUTI").get_all_records()
            tgl = datetime.strptime(tanggal, "%d/%m/%Y").date()

            # Proses cuti
            cuti_seharian = set()   # terapis yang cuti seharian (terencana/dadakan ALL)
            cuti_perjam = {}        # {(terapis, jam): tipe}
            dadakan_perjam = {}     # {(terapis, jam)} yang dadakan

            for c in all_cuti:
                try:
                    tgl_mulai = datetime.strptime(c["TGL_MULAI"], "%d/%m/%Y").date()
                    tgl_selesai = datetime.strptime(c["TGL_SELESAI"], "%d/%m/%Y").date()
                    if not (tgl_mulai <= tgl <= tgl_selesai):
                        continue
                    t = str(c["TERAPIS"]).upper()
                    jam_cuti = str(c.get("JAM","ALL")).strip().upper()
                    tipe = str(c.get("TIPE","terencana")).strip().lower()

                    if jam_cuti == "ALL":
                        cuti_seharian.add(t)
                        if tipe == "dadakan":
                            dadakan_perjam[t] = "ALL"
                    else:
                        jam_list = [j.strip() for j in jam_cuti.split(",") if j.strip()]
                        for jam_item in jam_list:
                            jam_norm = self._norm_jam(jam_item)
                            cuti_perjam[(t, jam_norm)] = tipe
                            if tipe == "dadakan":
                                dadakan_perjam[(t, jam_norm)] = True
                except Exception as ex:
                    log.error("Error parse cuti: " + str(ex))

            if cuti_seharian:
                log.info("Cuti seharian: " + str(cuti_seharian))
            if cuti_perjam:
                log.info("Cuti per jam: " + str(cuti_perjam))

            # Build config terapis (exclude yang cuti terencana seharian)
            config = {}
            for t in all_terapis:
                nama = str(t["TERAPIS"]).upper()
                jam = self._norm_jam(str(t["JAM"]))
                tipe = str(t["TIPE"]).lower()

                # Skip kalau cuti terencana seharian
                if nama in cuti_seharian and dadakan_perjam.get(nama) != "ALL":
                    continue

                # Skip kalau cuti terencana per jam
                if (nama, jam) in cuti_perjam and cuti_perjam[(nama, jam)] == "terencana":
                    continue

                # Skip kalau cuti dadakan seharian (tetap tidak dapat slot)
                if nama in cuti_seharian and dadakan_perjam.get(nama) == "ALL":
                    continue

                if nama not in config:
                    config[nama] = {"jams": set(), "tipe": tipe}
                config[nama]["jams"].add(jam)

            log.info("Terapis aktif: " + str(list(config.keys())))

            # Build dadakan_map: siapa yang cover siapa di jam mana
            # Prioritas cover: C dulu, lalu A/B
            dadakan_result = {}
            for key, val in dadakan_perjam.items():
                if isinstance(key, tuple):
                    t_cuti, jam_cuti = key
                    # Cari terapis cover di jam itu
                    cover = []
                    for t_cover in ["C","A","B","D"]:
                        if t_cover in config and jam_cuti in config[t_cover]["jams"]:
                            cover.append(t_cover)
                            break  # cukup 1 yang cover
                    dadakan_result[(t_cuti, jam_cuti)] = cover
                    log.info("Dadakan " + t_cuti + " jam " + jam_cuti + " -> cover: " + str(cover))

            return config, dadakan_result

        except Exception as e:
            log.error("Error _get_terapis_config: " + str(e))
            return {}, {}

    def _load_all_pasien(self):
        try:
            return self.sheets.get_worksheet("PASIEN").get_all_records()
        except Exception as e:
            log.error("Error _load_all_pasien: " + str(e))
            return []

    def _match_pasien(self, nama, all_pasien):
        if not all_pasien:
            return None
        try:
            names = [p["NAMA"] for p in all_pasien]
            match = process.extractOne(nama, names, scorer=fuzz.token_sort_ratio)
            if match and match[1] >= FUZZY_THRESHOLD:
                return all_pasien[names.index(match[0])]
            log.warning("Pasien tidak ditemukan: " + nama)
            return None
        except Exception as e:
            log.error("Error _match_pasien: " + str(e))
            return None

    @staticmethod
    def _norm_jam(j):
        try:
            parts = str(j).replace(".", ":").split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return str(h).zfill(2) + ":" + str(m).zfill(2)
        except Exception:
            return str(j)
