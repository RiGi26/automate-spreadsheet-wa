import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)
WITA = timezone(timedelta(hours=8))


class BlastClient:
    def __init__(self, sheets_client, fonnte_token, grup_id):
        self.sheets       = sheets_client
        self.fonnte_token = fonnte_token
        self.grup_id      = grup_id

    def kirim_rekap(self, assigned_rows, tanggal):
        import os
        if os.getenv("BLAST_ENABLED", "True").strip().lower() == "false":
            log.info("Blast dinonaktifkan (BLAST_ENABLED=False)")
            return False
        try:
            pesan = self._buat_pesan(assigned_rows, tanggal)
            if not pesan:
                log.warning("Pesan rekap kosong, tidak dikirim")
                return False
            return self._tulis_queue(pesan, tanggal)
        except Exception as e:
            log.error("Error kirim_rekap: " + str(e))
            return False

    def _tulis_queue(self, pesan, tanggal):
        try:
            ws        = self.sheets.get_worksheet("BLAST_QUEUE")
            timestamp = datetime.now(WITA).strftime("%d/%m/%Y %H:%M:%S")
            targets   = [g.strip() for g in str(self.grup_id).split(',') if g.strip()]
            if not targets:
                log.warning("GRUP_BLAST_ID tidak dikonfigurasi, blast dilewati")
                return False
            for target in targets:
                ws.append_row(["PENDING", pesan, timestamp, target], value_input_option="USER_ENTERED")
            log.info("Pesan rekap ditulis ke BLAST_QUEUE untuk %d grup" % len(targets))
            return True
        except Exception as e:
            log.error("Error _tulis_queue: " + str(e))
            return False

    def _nama_terapis(self, kode):
        import os
        mapping = {
            'A': os.getenv('NAMA_TERAPIS_A', 'A'),
            'B': os.getenv('NAMA_TERAPIS_B', 'B'),
            'C': os.getenv('NAMA_TERAPIS_C', 'C'),
            'D': os.getenv('NAMA_TERAPIS_D', 'D'),
        }
        return mapping.get(str(kode).upper(), kode)

    def _buat_pesan(self, assigned_rows, tanggal):
        try:
            from collections import defaultdict

            ws_pasien = self.sheets.get_worksheet("PASIEN")
            all_values = ws_pasien.get_all_values()
            if not all_values:
                all_pasien = []
            else:
                header = all_values[0]
                all_pasien = []
                for row in all_values[1:]:
                    if any(row):
                        all_pasien.append(dict(zip(header, row)))
            pasien_map = {}
            for p in all_pasien:
                pasien_map[str(p.get("NAMA","")).lower()] = p

            sesi_groups = defaultdict(list)
            for row in assigned_rows:
                key = (row.get("sesi",""), row.get("jam",""))
                sesi_groups[key].append(row)

            try:
                from datetime import datetime as dt
                tgl_obj  = dt.strptime(tanggal, "%d/%m/%Y")
                hari_map = {0:"Senin",1:"Selasa",2:"Rabu",3:"Kamis",4:"Jumat",5:"Sabtu",6:"Minggu"}
                bulan_map = {1:"Januari",2:"Februari",3:"Maret",4:"April",5:"Mei",6:"Juni",
                             7:"Juli",8:"Agustus",9:"September",10:"Oktober",11:"November",12:"Desember"}
                tgl_format = hari_map[tgl_obj.weekday()] + ", " + str(tgl_obj.day) + " " + bulan_map[tgl_obj.month] + " " + str(tgl_obj.year)
            except Exception:
                tgl_format = tanggal

            sesi_order = ["Sesi I","Sesi II","Sesi III","Sesi IV","Sesi V",
                          "Sesi VI","Sesi VII","Sesi VIII","Sesi IX","Sesi X",
                          "Sesi XI","Sesi XII"]
            sesi_icons = ["🕐","🕑","🕒","🕓","🕔","🕕","🕖","🕗","🕘","🕙","🕚","🕛"]

            sorted_sesi = sorted(
                sesi_groups.items(),
                key=lambda x: sesi_order.index(x[0][0]) if x[0][0] in sesi_order else 99
            )

            distribusi = defaultdict(int)
            lines = []
            lines.append("📋 *REKAP ASSIGNMENT TERAPIS*")
            lines.append("📅 " + tgl_format)
            lines.append("")

            for i, ((sesi, jam), pasien_list) in enumerate(sorted_sesi):
                icon    = sesi_icons[i] if i < len(sesi_icons) else "🕐"
                jam_fmt = jam.replace(":", ".") if jam else "-"
                lines.append("─────────────────────")
                lines.append(icon + " *" + sesi + " - " + jam_fmt + "*")

                for no, row in enumerate(pasien_list, 1):
                    nama    = row.get("nama", "-")
                    terapis = row.get("terapis", "-")
                    distribusi[terapis] += 1

                    tipe = "-"
                    nama_lower = str(nama).lower()
                    for key, data in pasien_map.items():
                        if nama_lower in key or key in nama_lower:
                            tipe = str(data.get("TIPE_PASIEN","")).strip() or "-"
                            break

                    lines.append(str(no) + ". " + nama + " | " + tipe + " → " + self._nama_terapis(terapis))

                lines.append("")

            lines.append("─────────────────────")
            lines.append("✅ *Total: " + str(len(assigned_rows)) + " pasien*")
            dist_parts = []
            for t in ["A","B","C","D"]:
                if distribusi.get(t, 0) > 0:
                    dist_parts.append(self._nama_terapis(t) + ": " + str(distribusi[t]))
            lines.append("👨‍⚕️ " + " | ".join(dist_parts))

            return "\n".join(lines)

        except Exception as e:
            log.error("Error _buat_pesan: " + str(e))
            return ""
