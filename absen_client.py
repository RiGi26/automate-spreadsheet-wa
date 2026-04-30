import logging
from datetime import datetime, timedelta
from rapidfuzz import fuzz, process

log = logging.getLogger(__name__)
FUZZY_THRESHOLD = 80
RIWAYAT_RETENTION_DAYS = 30

ROTASI = ["A", "B", "C", "D"]


class AbsenClient:
    def __init__(self, sheets_client):
        self.sheets = sheets_client

    def process_assignment(self, rows):
        if not rows:
            return rows

        tanggal = rows[0]["tanggal"]

        terapis_config, dadakan_map = self._get_terapis_config(tanggal)
        if not terapis_config:
            for r in rows:
                r["terapis"] = "MANUAL"
            return rows

        all_pasien  = self._load_all_pasien()
        riwayat_map = self._load_riwayat_terakhir()

        for row in rows:
            data = self._match_pasien(row["nama"], all_pasien)
            row["tipe_terapis"] = data.get("TIPE TERAPIS", "").strip().upper() if data else ""
            row["no_rm"]        = data.get("NO_RM", "") if data else ""

            nama_key = row["nama"].strip().lower()
            if nama_key in riwayat_map:
                row["terapis_terakhir"] = riwayat_map[nama_key]
                log.info("  Riwayat terakhir %s: %s" % (row["nama"], row["terapis_terakhir"]))
            elif row["tipe_terapis"] and row["tipe_terapis"] in ROTASI:
                idx = ROTASI.index(row["tipe_terapis"])
                row["terapis_terakhir"] = ROTASI[(idx - 1) % len(ROTASI)]
                log.info("  Pasien baru %s: tipe=%s set terakhir=%s" % (
                    row["nama"], row["tipe_terapis"], row["terapis_terakhir"]))
            else:
                row["terapis_terakhir"] = ""
                log.info("  Tidak ada data %s: bebas" % row["nama"])

        jam_groups = {}
        for row in rows:
            jam_groups.setdefault(row["jam"], []).append(row)

        quota_used = {}
        daily_used = {t: 0 for t in terapis_config}

        results = []
        for jam, pasien_list in jam_groups.items():
            quota_used[jam] = {}
            jam_quota = {}
            for t in terapis_config:
                if jam in terapis_config[t]["jams"]:
                    jam_quota[t] = 1

            for (t_cuti, j), cover_list in dadakan_map.items():
                if j == jam:
                    for t_cover in cover_list:
                        if t_cover in jam_quota:
                            jam_quota[t_cover] = jam_quota.get(t_cover, 0) + 1
                            log.info("Quota darurat %s di jam %s = %d (cover %s)" % (
                                t_cover, jam, jam_quota[t_cover], t_cuti))

            log.info("Jam %s quota: %s" % (jam, str(jam_quota)))

            for p in pasien_list:
                terakhir = p.get("terapis_terakhir", "")
                assigned = self._pick_terapis(jam_quota, quota_used[jam], daily_used, terakhir)
                p["terapis"] = assigned
                if assigned != "MANUAL":
                    quota_used[jam][assigned] = quota_used[jam].get(assigned, 0) + 1
                    daily_used[assigned]       = daily_used.get(assigned, 0) + 1
                log.info("  %s [jam %s] -> %s (terakhir: %s)" % (
                    p.get("nama", ""), jam, assigned, terakhir or "-"))

            results.extend(pasien_list)

        log.info("Distribusi harian: %s" % str(dict(daily_used)))
        return results

    def _pick_terapis(self, jam_quota, jam_used, daily_used, terakhir):
        def has_quota(t):
            return jam_used.get(t, 0) < jam_quota.get(t, 0)
        def available(t):
            return t in jam_quota and has_quota(t)

        if terakhir and terakhir in ROTASI:
            idx = ROTASI.index(terakhir)
            for i in range(1, len(ROTASI) + 1):
                kandidat = ROTASI[(idx + i) % len(ROTASI)]
                if available(kandidat):
                    return kandidat

        candidates = [t for t in ROTASI if available(t)]
        if candidates:
            return min(candidates, key=lambda x: daily_used.get(x, 0))

        candidates2 = [t for t in ROTASI if t in jam_quota]
        if candidates2:
            t = min(candidates2, key=lambda x: daily_used.get(x, 0))
            log.warning("Override quota -> %s" % t)
            return t

        return "MANUAL"

    def update_after_assignment(self, assigned_rows):
        try:
            SESI_ORDER = {
                "Sesi I": 1, "Sesi II": 2, "Sesi III": 3, "Sesi IV": 4,
                "Sesi V": 5, "Sesi VI": 6, "Sesi VII": 7, "Sesi VIII": 8,
                "Sesi IX": 9, "Sesi X": 10, "Sesi XI": 11, "Sesi XII": 12
            }
            sorted_rows = sorted(
                [r for r in assigned_rows if r.get("terapis") != "MANUAL"],
                key=lambda r: (SESI_ORDER.get(r.get("sesi", ""), 99), r.get("jam", ""))
            )
            riwayat = []
            for row in sorted_rows:
                riwayat.append([
                    row.get("timestamp", ""), row.get("tanggal", ""),
                    row.get("nama", ""),      row.get("no_rm", ""),
                    row.get("sesi", ""),      row.get("jam", ""),
                    row.get("terapis", "")
                ])
            if riwayat:
                self.sheets.get_worksheet("RIWAYAT").append_rows(riwayat, value_input_option="USER_ENTERED")
                log.info("Catat %d baris ke RIWAYAT (sorted by sesi)" % len(riwayat))
        except Exception as e:
            log.error("Error update_after_assignment: " + str(e))
            raise

    def hapus_riwayat_lama(self, days=RIWAYAT_RETENTION_DAYS):
        try:
            ws = self.sheets.get_worksheet("RIWAYAT")
            all_records = ws.get_all_records()
            cutoff = datetime.now().date() - timedelta(days=days)
            header = ["TIMESTAMP", "TANGGAL", "NAMA", "NO_RM", "SESI", "JAM", "TERAPIS"]
            keep, deleted = [], 0
            for r in all_records:
                try:
                    if datetime.strptime(r["TANGGAL"], "%d/%m/%Y").date() >= cutoff:
                        keep.append([r.get(h, "") for h in header])
                    else:
                        deleted += 1
                except Exception:
                    keep.append([r.get(h, "") for h in header])
            if deleted > 0:
                ws.clear()
                ws.append_row(header)
                if keep:
                    ws.append_rows(keep, value_input_option="USER_ENTERED")
                log.info("Auto-delete: hapus %d riwayat lama" % deleted)
        except Exception as e:
            log.error("Error hapus_riwayat_lama: " + str(e))

    def _load_riwayat_terakhir(self):
        try:
            ws = self.sheets.get_worksheet("RIWAYAT")
            records = ws.get_all_records()
            if not records:
                return {}
            def parse_ts(r):
                try:
                    return datetime.strptime(str(r.get("TIMESTAMP", "")), "%d/%m/%Y %H:%M:%S")
                except Exception:
                    return datetime.min
            records_sorted = sorted(records, key=parse_ts, reverse=True)
            hasil = {}
            for r in records_sorted:
                nama    = str(r.get("NAMA", "")).strip().lower()
                terapis = str(r.get("TERAPIS", "")).strip().upper()
                if nama and terapis and nama not in hasil:
                    hasil[nama] = terapis
            log.info("Load riwayat terakhir: %d pasien" % len(hasil))
            return hasil
        except Exception as e:
            log.error("Error _load_riwayat_terakhir: " + str(e))
            return {}

    def _get_terapis_config(self, tanggal):
        try:
            all_terapis = self.sheets.get_worksheet("TERAPIS").get_all_records()
            all_cuti    = self.sheets.get_worksheet("CUTI").get_all_records()
            tgl = datetime.strptime(tanggal, "%d/%m/%Y").date()
            cuti_seharian  = set()
            cuti_perjam    = {}
            dadakan_perjam = {}
            for c in all_cuti:
                try:
                    tgl_mulai   = datetime.strptime(c["TGL_MULAI"],   "%d/%m/%Y").date()
                    tgl_selesai = datetime.strptime(c["TGL_SELESAI"], "%d/%m/%Y").date()
                    if not (tgl_mulai <= tgl <= tgl_selesai):
                        continue
                    t        = str(c["TERAPIS"]).upper()
                    jam_cuti = str(c.get("JAM", "ALL")).strip().upper()
                    tipe     = str(c.get("TIPE", "terencana")).strip().lower()
                    if jam_cuti == "ALL":
                        cuti_seharian.add(t)
                        if tipe == "dadakan":
                            dadakan_perjam[t] = "ALL"
                    else:
                        for jam_item in [j.strip() for j in jam_cuti.split(",") if j.strip()]:
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
            config = {}
            for t in all_terapis:
                nama = str(t["TERAPIS"]).upper()
                jam  = self._norm_jam(str(t["JAM"]))
                tipe = str(t["TIPE"]).lower()
                if nama in cuti_seharian and dadakan_perjam.get(nama) != "ALL":
                    continue
                if (nama, jam) in cuti_perjam and cuti_perjam[(nama, jam)] == "terencana":
                    continue
                if nama in cuti_seharian and dadakan_perjam.get(nama) == "ALL":
                    continue
                if nama not in config:
                    config[nama] = {"jams": set(), "tipe": tipe}
                config[nama]["jams"].add(jam)
            log.info("Terapis aktif: " + str(list(config.keys())))
            dadakan_result = {}
            for key, val in dadakan_perjam.items():
                if isinstance(key, tuple):
                    t_cuti, jam_cuti = key
                    cover = []
                    for t_cover in ["C", "A", "B", "D"]:
                        if t_cover in config and jam_cuti in config[t_cover]["jams"]:
                            cover.append(t_cover)
                            break
                    dadakan_result[(t_cuti, jam_cuti)] = cover
                    log.info("Dadakan %s jam %s -> cover: %s" % (t_cuti, jam_cuti, str(cover)))
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
            match = process.extractOne(nama, names, scorer=fuzz.token_set_ratio)
            if match and match[1] >= FUZZY_THRESHOLD:
                log.info("Match: '%s' -> '%s' (score=%d)" % (nama, match[0], match[1]))
                return all_pasien[names.index(match[0])]
            match2 = process.extractOne(nama, names, scorer=fuzz.partial_ratio)
            if match2 and match2[1] >= 90:
                log.info("Partial match: '%s' -> '%s' (score=%d)" % (nama, match2[0], match2[1]))
                return all_pasien[names.index(match2[0])]
            log.warning("Pasien tidak ditemukan: '%s'" % nama)
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
