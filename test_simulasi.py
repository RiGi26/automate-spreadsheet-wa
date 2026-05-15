"""
test_simulasi.py — Simulasi semua skenario assignment tanpa koneksi Google Sheets

Data acuan dari sheet Jadwal (Trial Automation.xlsx):
  27 pasien aktif, 9 sesi, masing-masing 3 pasien per sesi (data 29/04/2026)

Jalankan: python test_simulasi.py
"""

ROTASI = ["A", "B", "C", "D"]

TERAPIS_CONFIG = {
    "A": {"jams": {"09:00": 2, "10:00": 2, "10:30": 2, "11:00": 2, "14:00": 2, "14:30": 2, "15:00": 2}},
    "B": {"jams": {"08:00": 2, "08:30": 2, "09:00": 2, "10:00": 2, "10:30": 2, "11:00": 2, "14:00": 2, "14:30": 2, "15:00": 2}},
    "C": {"jams": {"08:00": 3, "08:30": 3, "09:00": 3, "10:00": 3, "10:30": 3, "11:00": 3, "14:00": 3, "14:30": 3, "15:00": 3}},
    "D": {"jams": {"08:00": 1, "08:30": 1}},
}

# Data nyata dari sheet Jadwal (29/04/2026) — 27 pasien, 9 sesi x 3 pasien
JADWAL_NYATA = [
    ("08:00", ["M. Rayhan",          "Rasya Nugraha",         "Khaula zia"]),
    ("08:30", ["Kenneth Athallah",   "Anindira Fauziah",      "M. Ibrahim"]),
    ("09:00", ["Sarah Prastyaning",  "M. Akbar Alghazi",      "Eqrem Rasya"]),
    ("10:00", ["Al fath Jassem",     "M. Ghazali Faiz",       "Chintya Anggiana Alesha"]),
    ("10:30", ["M. Alvino",          "Alifia Zea Amanda",     "Muhammad Luthfi Abian"]),
    ("11:00", ["Sheo Nawasena",      "Zhafira Ghea",          "Aqila Ghaniyah"]),
    ("14:00", ["Gevariel Pardede",   "Hafiz Alvarendra",      "Ibni Abbad"]),
    ("14:30", ["M. Nizar Wardana",   "Rizki Maruli",          "Hayfa Marwah"]),
    ("15:00", ["Raina Caramellia",   "Bachrudin Pratama",     "Al fateh Nur Zahwan"]),
]

# TIPE TERAPIS dari sheet PASIEN (hasil fuzzy match)
TIPE_TERAPIS = {
    "rasya nugraha":          "B",
    "kenneth athallah":       "B",
    "eqrem rasya":            "A",
    "chintya anggiana alesha":"A",
    "gevariel pardede":       "C",
    "hafiz alvarendra":       "A",
    "al fateh nur zahwan":    "A",
}

# Hasil assignment nyata dari sheet RIWAYAT (29/04/2026)
RIWAYAT_NYATA = {
    "M. Rayhan":               "B",
    "Rasya Nugraha":           "C",
    "Khaula zia":              "D",
    "Kenneth Athallah":        "B",
    "Anindira Fauziah":        "C",
    "M. Ibrahim":              "D",
    "Sarah Prastyaning":       "A",
    "M. Akbar Alghazi":        "B",
    "Eqrem Rasya":             "C",
    "Al fath Jassem":          "C",
    "M. Ghazali Faiz":         "A",
    "Chintya Anggiana Alesha": "B",
    "M. Alvino":               "A",
    "Alifia Zea Amanda":       "B",
    "Muhammad Luthfi Abian":   "C",
    "Sheo Nawasena":           "A",
    "Zhafira Ghea":            "B",
    "Aqila Ghaniyah":          "C",
    "Gevariel Pardede":        "C",
    "Hafiz Alvarendra":        "A",
    "Ibni Abbad":              "B",
    "M. Nizar Wardana":        "B",
    "Rizki Maruli":            "A",
    "Hayfa Marwah":            "C",
    "Raina Caramellia":        "B",
    "Bachrudin Pratama":       "A",
    "Al fateh Nur Zahwan":     "C",
}

PASS = 0
FAIL = 0


def _pick_terapis(jam_quota, jam_used, daily_used, terakhir, maks_harian):
    def has_quota(t):
        return jam_used.get(t, 0) < jam_quota.get(t, 0)
    def within_daily(t):
        return daily_used.get(t, 0) < maks_harian.get(t, 999)
    def available(t):
        return t in jam_quota and has_quota(t) and within_daily(t)

    if terakhir and terakhir in ROTASI:
        idx = ROTASI.index(terakhir)
        for i in range(1, len(ROTASI) + 1):
            kandidat = ROTASI[(idx + i) % len(ROTASI)]
            if available(kandidat):
                return kandidat

    candidates = [t for t in ROTASI if available(t)]
    if candidates:
        return min(candidates, key=lambda x: daily_used.get(x, 0))

    # Fallback 1: slot penuh tapi masih dalam batas harian — overflow slot
    candidates2 = [t for t in ROTASI if t in jam_quota and within_daily(t)]
    if candidates2:
        return min(candidates2, key=lambda x: daily_used.get(x, 0))

    # Fallback 2: slot masih ada tapi daily sudah maks — overflow daily
    candidates3 = [t for t in ROTASI if t in jam_quota and has_quota(t)]
    if candidates3:
        return min(candidates3, key=lambda x: daily_used.get(x, 0))

    # Fallback 3 (last resort): abaikan semua constraint
    candidates4 = [t for t in ROTASI if t in jam_quota]
    if candidates4:
        return min(candidates4, key=lambda x: daily_used.get(x, 0))

    return "MANUAL"


def assign_session(pasien_list, jam, maks_harian, daily_used=None):
    """Assign satu session. Kembalikan (results, daily_used)."""
    if daily_used is None:
        daily_used = {t: 0 for t in ROTASI}

    jam_quota = {}
    for t in TERAPIS_CONFIG:
        if jam in TERAPIS_CONFIG[t]["jams"]:
            jam_quota[t] = TERAPIS_CONFIG[t]["jams"][jam]

    jam_used  = {}
    results   = []
    for p in pasien_list:
        terakhir = p.get("terakhir", "")
        assigned = _pick_terapis(jam_quota, jam_used, daily_used, terakhir, maks_harian)
        jam_used[assigned]  = jam_used.get(assigned, 0) + 1
        daily_used[assigned] = daily_used.get(assigned, 0) + 1
        results.append({**p, "assigned": assigned})
    return results, daily_used


def enforce_maks(maks_dari_sheet):
    maks = dict(maks_dari_sheet)
    maks["D"] = 2
    maks_a = maks.get("A")
    maks_b = maks.get("B")
    if maks_a is not None and maks_b is None:
        maks["B"] = maks_a
    elif maks_b is not None and maks_a is None:
        maks["A"] = maks_b
    return maks


# ─── Helper ───────────────────────────────────────────────
def cek(label, kondisi, detail=""):
    global PASS, FAIL
    status = "PASS" if kondisi else "FAIL"
    if kondisi:
        PASS += 1
    else:
        FAIL += 1
    suffix = ("  -> " + detail) if detail else ""
    print("  [%s] %s%s" % (status, label, suffix))


def header(judul):
    print()
    print("=" * 60)
    print("  %s" % judul)
    print("=" * 60)


# ══════════════════════════════════════════════════════════
# SKENARIO 1: First visit — pasien baru dengan TIPE TERAPIS
# ══════════════════════════════════════════════════════════
header("SKENARIO 1: First visit menggunakan first_terapis")
print("  Rule: pasien baru dengan TIPE TERAPIS=X harus dapat X di kunjungan pertama")
print("  Catatan: D hanya punya slot 08:00 dan 08:30 (tidak ada di 09:00+)")
print()

# A, B, C ditest di 09:00 (semua tersedia)
for tipe in ["A", "B", "C"]:
    idx      = ROTASI.index(tipe)
    terakhir = ROTASI[(idx - 1) % len(ROTASI)]
    hasil, _ = assign_session(
        [{"nama": "Pasien Baru", "terakhir": terakhir}],
        jam="09:00",
        maks_harian={}
    )
    got = hasil[0]["assigned"]
    cek("TIPE=%s di slot 09:00 -> dapat %s" % (tipe, got), got == tipe,
        "seharusnya %s" % tipe)

# D ditest di 08:00 (satu-satunya slot D)
idx_d    = ROTASI.index("D")
terakhir = ROTASI[(idx_d - 1) % len(ROTASI)]
hasil, _ = assign_session(
    [{"nama": "Pasien Baru D", "terakhir": terakhir}],
    jam="08:00",
    maks_harian={}
)
got = hasil[0]["assigned"]
cek("TIPE=D di slot 08:00 -> dapat %s" % got, got == "D",
    "seharusnya D")

# ══════════════════════════════════════════════════════════
# SKENARIO 2: Return visit — rotasi dari terakhir
# ══════════════════════════════════════════════════════════
header("SKENARIO 2: Return visit — rotasi dari terapis terakhir")
print("  Rule: kunjungan berikutnya dapat terapis berikutnya yang TERSEDIA di slot itu")
print("  Catatan: D tidak tersedia di 09:00, jadi C->D di slot 09:00 melompat ke A")
print()

# Di slot 09:00: A, B, C tersedia. D tidak ada.
rotasi_09 = {"A": "B", "B": "C", "C": "A", "D": "A"}
for terakhir, expected in rotasi_09.items():
    hasil, _ = assign_session(
        [{"nama": "Pasien Lama", "terakhir": terakhir}],
        jam="09:00",
        maks_harian={}
    )
    got = hasil[0]["assigned"]
    cek("Slot 09:00, terakhir=%s -> dapat %s" % (terakhir, got), got == expected,
        "seharusnya %s (D tidak ada di slot ini)" % expected if terakhir == "C" else "seharusnya %s" % expected)

# Di slot 08:00: B, C, D tersedia. A tidak ada.
print()
rotasi_08 = {"A": "B", "B": "C", "C": "D", "D": "B"}
for terakhir, expected in rotasi_08.items():
    hasil, _ = assign_session(
        [{"nama": "Pasien Lama", "terakhir": terakhir}],
        jam="08:00",
        maks_harian={}
    )
    got = hasil[0]["assigned"]
    cek("Slot 08:00, terakhir=%s -> dapat %s" % (terakhir, got), got == expected,
        "seharusnya %s (A tidak ada di slot ini)" % expected if terakhir == "D" else "seharusnya %s" % expected)

# ══════════════════════════════════════════════════════════
# SKENARIO 3: Kapasitas slot — tidak ada override
# ══════════════════════════════════════════════════════════
header("SKENARIO 3: Kapasitas slot dari TERAPIS sheet")
print("  Slot 08:00: B=2, C=3, D=1 => maks 6 pasien tanpa override")
print()

pasien_6 = [{"nama": "Pasien %d" % i, "terakhir": ""} for i in range(1, 7)]
hasil, daily = assign_session(pasien_6, jam="08:00", maks_harian={})

distribusi = {}
for r in hasil:
    distribusi[r["assigned"]] = distribusi.get(r["assigned"], 0) + 1

cek("6 pasien di slot 08:00 tanpa MANUAL",
    all(r["assigned"] != "MANUAL" for r in hasil),
    str(distribusi))
cek("B tidak melebihi kapasitas 2",
    distribusi.get("B", 0) <= 2)
cek("C tidak melebihi kapasitas 3",
    distribusi.get("C", 0) <= 3)
cek("D tidak melebihi kapasitas 1",
    distribusi.get("D", 0) <= 1)

print()
print("  Slot 08:00: 7 pasien (melebihi kapasitas 6)")
pasien_7 = [{"nama": "Pasien %d" % i, "terakhir": ""} for i in range(1, 8)]
hasil7, _ = assign_session(pasien_7, jam="08:00", maks_harian={})
ada_fallback = any(r["assigned"] in ("B", "C", "D") for r in hasil7)
cek("7 pasien tetap ter-assign (fallback aktif)",
    all(r["assigned"] != "MANUAL" for r in hasil7))

# ══════════════════════════════════════════════════════════
# SKENARIO 4: Dua pasien terakhir sama di slot yang sama
# ══════════════════════════════════════════════════════════
header("SKENARIO 4: Beberapa pasien dengan terakhir sama di slot yang sama")
print("  Rule: tidak ada terapis yang melebihi KAPASITAS slot-nya")
print("  Catatan: B kapasitas=2 di 09:00, jadi 2 pasien di B adalah VALID (bukan double)")
print()

pasien_sama = [
    {"nama": "Pasien 1", "terakhir": "A"},
    {"nama": "Pasien 2", "terakhir": "A"},
    {"nama": "Pasien 3", "terakhir": "A"},
    {"nama": "Pasien 4", "terakhir": "A"},
    {"nama": "Pasien 5", "terakhir": "A"},
]
hasil_sama, _ = assign_session(pasien_sama, jam="09:00", maks_harian={})
distribusi = {}
for r in hasil_sama:
    t = r["assigned"]
    distribusi[t] = distribusi.get(t, 0) + 1
    print("  %s -> %s" % (r["nama"], t))

kap = TERAPIS_CONFIG
cek("B tidak melebihi kapasitas 2 di slot 09:00",
    distribusi.get("B", 0) <= kap["B"]["jams"].get("09:00", 0),
    "B=%d/2" % distribusi.get("B", 0))
cek("C tidak melebihi kapasitas 3 di slot 09:00",
    distribusi.get("C", 0) <= kap["C"]["jams"].get("09:00", 0),
    "C=%d/3" % distribusi.get("C", 0))
cek("Semua 5 pasien ter-assign (tidak ada MANUAL)",
    all(r["assigned"] != "MANUAL" for r in hasil_sama),
    str(distribusi))

# ══════════════════════════════════════════════════════════
# SKENARIO 5: MAKS_HARIAN — terapis penuh dialihkan
# ══════════════════════════════════════════════════════════
header("SKENARIO 5: MAKS_HARIAN — terapis yang sudah penuh dilewati")
print()

maks = {"A": 2, "B": 2, "C": 10, "D": 2}
daily = {"A": 2, "B": 0, "C": 0, "D": 0}  # A sudah penuh
hasil5, _ = assign_session(
    [{"nama": "Pasien X", "terakhir": "D"}],  # seharusnya dapat A
    jam="09:00",
    maks_harian=maks,
    daily_used=daily
)
got5 = hasil5[0]["assigned"]
cek("Seharusnya dapat A tapi A penuh -> dapat %s (bukan A)" % got5,
    got5 != "A",
    "A sudah maks 2, dialihkan ke %s" % got5)

daily2 = {"A": 2, "B": 2, "C": 0, "D": 0}  # A dan B sudah penuh
hasil5b, _ = assign_session(
    [{"nama": "Pasien Y", "terakhir": "D"}],
    jam="09:00",
    maks_harian=maks,
    daily_used=daily2
)
got5b = hasil5b[0]["assigned"]
cek("A dan B penuh -> dapat C (%s)" % got5b, got5b == "C")

# ══════════════════════════════════════════════════════════
# SKENARIO 6: Rule validasi MAKS_TERAPIS (A=B±1, C>max(A,B), D=2)
# ══════════════════════════════════════════════════════════
header("SKENARIO 6: Validasi rule MAKS_TERAPIS")
print()

kasus_maks = [
    ("A=8, B=8 (sama, valid)",       {"A": 8, "B": 8,  "C": 14}, True,  False, False),
    ("A=9, B=8 (beda 1, valid)",     {"A": 9, "B": 8,  "C": 14}, False, False, False),
    ("A=9, B=7 (beda 2, warn)",      {"A": 9, "B": 7,  "C": 14}, False, True,  False),
    ("C=8 <= max(A,B)=8 (warn)",     {"A": 8, "B": 8,  "C": 8},  False, False, True),
    ("C=7 < A=8 (warn)",             {"A": 8, "B": 8,  "C": 7},  False, False, True),
    ("D selalu 2 meski sheet D=5",   {"A": 8, "B": 8,  "C": 14, "D": 5}, False, False, False),
]

for label, sheet, _, warn_ab, warn_c in kasus_maks:
    maks = enforce_maks(sheet)
    diff_ab = abs(maks.get("A", 0) - maks.get("B", 0)) if "A" in maks and "B" in maks else 0
    ab_vals = [maks[k] for k in ("A", "B") if k in maks]
    max_ab  = max(ab_vals) if ab_vals else 0
    c_val   = maks.get("C", 999)
    d_val   = maks.get("D")

    got_warn_ab = diff_ab > 1
    got_warn_c  = c_val <= max_ab if "C" in maks else False
    d_ok        = d_val == 2

    cek(label,
        got_warn_ab == warn_ab and got_warn_c == warn_c and d_ok,
        "D=%s, |A-B|=%d, C%s>max(A,B)=%d" % (d_val, diff_ab, "" if not got_warn_c else " TIDAK", max_ab))

# ══════════════════════════════════════════════════════════
# SKENARIO 7: D selalu maks 2 per hari
# ══════════════════════════════════════════════════════════
header("SKENARIO 7: D tidak boleh lebih dari 2 pasien per hari")
print()

maks7   = {"A": 20, "B": 20, "C": 20, "D": 2}
daily7  = {"A": 0, "B": 0, "C": 0, "D": 2}  # D sudah dapat 2
hasil7a, _ = assign_session(
    [{"nama": "Pasien Z", "terakhir": "C"}],  # rotasi ke D
    jam="08:00",
    maks_harian=maks7,
    daily_used=daily7
)
got7 = hasil7a[0]["assigned"]
cek("D sudah maks 2 -> pasien dialihkan ke %s (bukan D)" % got7, got7 != "D")

# ══════════════════════════════════════════════════════════
# SKENARIO 8: Simulasi data NYATA dari sheet Jadwal (27 pasien, 9 sesi)
# ══════════════════════════════════════════════════════════
header("SKENARIO 8: Simulasi data nyata Jadwal (27 pasien, 9 sesi x 3 pasien)")
print("  Sumber: sheet Jadwal tanggal 29/04/2026")
print("  TIPE TERAPIS diambil dari sheet PASIEN via fuzzy match")
print()

maks8   = {"A": 9, "B": 8, "C": 17, "D": 2}  # dari sheet MAKS_TERAPIS trial
daily8  = {t: 0 for t in ROTASI}

for jam, nama_list in JADWAL_NYATA:
    pasien_sesi = []
    for nama in nama_list:
        tipe     = TIPE_TERAPIS.get(nama.lower(), "")
        idx_tipe = ROTASI.index(tipe) if tipe in ROTASI else -1
        # first visit: terakhir = prev(tipe) agar dapat tipe itu sendiri
        terakhir = ROTASI[(idx_tipe - 1) % len(ROTASI)] if idx_tipe >= 0 else ""
        pasien_sesi.append({"nama": nama, "terakhir": terakhir})
    _, daily8 = assign_session(pasien_sesi, jam=jam, maks_harian=maks8, daily_used=daily8)

print("  Distribusi hasil simulasi: A=%d, B=%d, C=%d, D=%d (total=%d)" % (
    daily8.get("A",0), daily8.get("B",0), daily8.get("C",0), daily8.get("D",0),
    sum(daily8.values())))
print("  Distribusi data nyata (RIWAYAT): A=7, B=9, C=9, D=2")
print()
cek("Total pasien ter-assign = 27", sum(daily8.values()) == 27,
    "total=%d" % sum(daily8.values()))
cek("D tidak melebihi 2", daily8.get("D", 0) <= 2,
    "D=%d" % daily8.get("D", 0))
cek("A tidak melebihi MAKS_A=9", daily8.get("A", 0) <= 9,
    "A=%d" % daily8.get("A", 0))
cek("B tidak melebihi MAKS_B=8", daily8.get("B", 0) <= 8,
    "B=%d" % daily8.get("B", 0))
cek("|A - B| tidak lebih dari 1",
    abs(daily8.get("A", 0) - daily8.get("B", 0)) <= 1,
    "|A-B|=%d" % abs(daily8.get("A", 0) - daily8.get("B", 0)))

print()
# ── Skenario 8b: dengan MAKS yang lebih ketat ─────────────
print("  Dengan MAKS lebih ketat (A=7, B=7, C=17): sisa pasien overflow ke C")
maks8b  = {"A": 7, "B": 7, "C": 17, "D": 2}
daily8b = {t: 0 for t in ROTASI}
for jam, nama_list in JADWAL_NYATA:
    pasien_sesi = []
    for nama in nama_list:
        tipe     = TIPE_TERAPIS.get(nama.lower(), "")
        idx_tipe = ROTASI.index(tipe) if tipe in ROTASI else -1
        terakhir = ROTASI[(idx_tipe - 1) % len(ROTASI)] if idx_tipe >= 0 else ""
        pasien_sesi.append({"nama": nama, "terakhir": terakhir})
    _, daily8b = assign_session(pasien_sesi, jam=jam, maks_harian=maks8b, daily_used=daily8b)

print("  Distribusi: A=%d, B=%d, C=%d, D=%d" % (
    daily8b.get("A",0), daily8b.get("B",0), daily8b.get("C",0), daily8b.get("D",0)))
cek("A tidak melebihi MAKS_A=7", daily8b.get("A", 0) <= 7)
cek("B tidak melebihi MAKS_B=7", daily8b.get("B", 0) <= 7)
cek("C mendapat lebih banyak dari A",
    daily8b.get("C", 0) > daily8b.get("A", 0),
    "C=%d, A=%d" % (daily8b.get("C", 0), daily8b.get("A", 0)))
cek("C mendapat lebih banyak dari B",
    daily8b.get("C", 0) > daily8b.get("B", 0),
    "C=%d, B=%d" % (daily8b.get("C", 0), daily8b.get("B", 0)))

# ══════════════════════════════════════════════════════════
# RINGKASAN
# ══════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════
# SKENARIO 9: Cuti terencana per jam
# ══════════════════════════════════════════════════════════
header("SKENARIO 9: Cuti terencana per jam")
print("  A cuti terencana di 09:00 -> A tidak boleh dapat pasien di slot itu")
print()

TERAPIS_CONFIG_CUTI = {
    "A": {"jams": {"10:00": 2, "10:30": 2, "11:00": 2, "14:00": 2}},  # 09:00 dihapus
    "B": {"jams": {"08:00": 2, "08:30": 2, "09:00": 2, "10:00": 2}},
    "C": {"jams": {"08:00": 3, "08:30": 3, "09:00": 3, "10:00": 3}},
    "D": {"jams": {"08:00": 1, "08:30": 1}},
}

def assign_session_custom(pasien_list, jam, maks_harian, terapis_cfg, daily_used=None):
    if daily_used is None:
        daily_used = {t: 0 for t in ROTASI}
    jam_quota = {}
    for t in terapis_cfg:
        if jam in terapis_cfg[t]["jams"]:
            jam_quota[t] = terapis_cfg[t]["jams"][jam]
    jam_used = {}
    results  = []
    for p in pasien_list:
        assigned = _pick_terapis(jam_quota, jam_used, daily_used, p.get("terakhir", ""), maks_harian)
        jam_used[assigned]   = jam_used.get(assigned, 0) + 1
        daily_used[assigned] = daily_used.get(assigned, 0) + 1
        results.append({**p, "assigned": assigned})
    return results, daily_used

pasien_09 = [{"nama": "P%d" % i, "terakhir": ""} for i in range(1, 4)]
hasil9, _ = assign_session_custom(pasien_09, "09:00", {}, TERAPIS_CONFIG_CUTI)
terapis_dapat9 = [r["assigned"] for r in hasil9]
cek("A tidak dapat pasien di slot cuti 09:00",
    "A" not in terapis_dapat9,
    "dapat: %s" % terapis_dapat9)
cek("Semua pasien tetap ter-assign (bukan MANUAL)",
    all(r["assigned"] != "MANUAL" for r in hasil9),
    str(terapis_dapat9))

# ══════════════════════════════════════════════════════════
# SKENARIO 10: Cuti dadakan per jam + cover quota
# ══════════════════════════════════════════════════════════
header("SKENARIO 10: Cuti dadakan per jam")
print("  A cuti dadakan 09:00,10:00,10:30 (dari data CUTI nyata 25/04/2026)")
print("  -> A dihapus dari slot tersebut, cover (C) dapat +1 quota")
print()

# Simulasi: slot 09:00, A absen, C dapat quota normal + 1 extra (cover A)
TERAPIS_DADAKAN = {
    "A": {"jams": {"10:00": 2, "14:00": 2, "14:30": 2, "15:00": 2}},  # 09:00,10:30,11:00 dihapus
    "B": {"jams": {"08:00": 2, "08:30": 2, "09:00": 2, "10:00": 2, "10:30": 2, "11:00": 2}},
    "C": {"jams": {"08:00": 3, "08:30": 3, "09:00": 3, "10:00": 3, "10:30": 3, "11:00": 3}},
    "D": {"jams": {"08:00": 1, "08:30": 1}},
}

# Di slot 09:00: A tidak ada, C mendapat +1 cover quota (total 3+1=4)
jam_quota_dadakan = {"B": 2, "C": 3 + 1}  # C cover A
jam_used_d = {}
daily_d    = {t: 0 for t in ROTASI}

# 5 pasien di 09:00 (melebihi kapasitas normal B+C=5, tapi C ada +1 jadi total 6)
pasien_dadakan = [{"nama": "P%d" % i, "terakhir": ""} for i in range(1, 6)]
hasil10 = []
for p in pasien_dadakan:
    assigned = _pick_terapis(jam_quota_dadakan, jam_used_d, daily_d, p.get("terakhir", ""), {})
    jam_used_d[assigned]  = jam_used_d.get(assigned, 0) + 1
    daily_d[assigned]     = daily_d.get(assigned, 0) + 1
    hasil10.append({**p, "assigned": assigned})

dist10 = {}
for r in hasil10:
    dist10[r["assigned"]] = dist10.get(r["assigned"], 0) + 1

cek("A tidak dapat pasien di slot dadakan",
    "A" not in dist10,
    "distribusi: %s" % dist10)
cek("B tidak melebihi kapasitas 2",
    dist10.get("B", 0) <= 2,
    "B=%d" % dist10.get("B", 0))
cek("C tidak melebihi kapasitas cover (3+1=4)",
    dist10.get("C", 0) <= 4,
    "C=%d/4" % dist10.get("C", 0))
cek("Semua 5 pasien ter-assign",
    all(r["assigned"] != "MANUAL" for r in hasil10),
    str(dist10))

# ══════════════════════════════════════════════════════════
# SKENARIO 11: Cuti terencana seharian
# ══════════════════════════════════════════════════════════
header("SKENARIO 11: Cuti terencana seharian")
print("  B cuti terencana ALL (dari data CUTI nyata 26/04/2026)")
print("  -> B tidak boleh dapat pasien di hari itu sama sekali")
print()

TERAPIS_TANPA_B = {
    "A": {"jams": {"09:00": 2, "10:00": 2, "10:30": 2, "11:00": 2}},
    "C": {"jams": {"08:00": 3, "08:30": 3, "09:00": 3, "10:00": 3}},
    "D": {"jams": {"08:00": 1, "08:30": 1}},
}

daily11 = {t: 0 for t in ROTASI}
all_hasil11 = []
for jam11, n11 in [("08:00", 3), ("09:00", 3), ("10:00", 3)]:
    pasien11 = [{"nama": "P%d" % i, "terakhir": ""} for i in range(n11)]
    h11, daily11 = assign_session_custom(pasien11, jam11, {}, TERAPIS_TANPA_B, daily11)
    all_hasil11.extend(h11)

cek("B tidak dapat pasien sama sekali",
    all(r["assigned"] != "B" for r in all_hasil11),
    "distribusi: %s" % {r["assigned"]: sum(1 for x in all_hasil11 if x["assigned"]==r["assigned"]) for r in all_hasil11})
cek("Semua 9 pasien ter-assign",
    all(r["assigned"] != "MANUAL" for r in all_hasil11))

# ══════════════════════════════════════════════════════════
# SKENARIO 12: Duplikat webhook dari Fonnte — filter_duplikat
# ══════════════════════════════════════════════════════════
header("SKENARIO 12: Duplikat webhook dari Fonnte (filter_duplikat)")
print("  Simulasi Fonnte kirim webhook 2x dengan data persis sama")
print()

def simulasi_filter_duplikat(existing_rows, incoming_rows):
    """Tiruan logika filter_duplikat dari sheets_client.py."""
    if not incoming_rows:
        return incoming_rows
    tanggal_cek = incoming_rows[0]['tanggal']
    existing_keys = {
        (r['tanggal'], r['sesi'], r['nama'].strip().lower())
        for r in existing_rows
        if r['tanggal'] == tanggal_cek
    }
    baru = [
        r for r in incoming_rows
        if (r['tanggal'], r['sesi'], r['nama'].strip().lower()) not in existing_keys
    ]
    return baru

# Data webhook pertama
webhook1 = [
    {'tanggal': '29/04/2026', 'sesi': 'Sesi I',  'nama': 'M. Rayhan',   'jam': '08:00'},
    {'tanggal': '29/04/2026', 'sesi': 'Sesi I',  'nama': 'Rasya Nugraha','jam': '08:00'},
    {'tanggal': '29/04/2026', 'sesi': 'Sesi II', 'nama': 'Kenneth',      'jam': '08:30'},
]

# Webhook kedua persis sama (duplikat Fonnte)
webhook2 = list(webhook1)

# Setelah webhook pertama tersimpan, webhook kedua harus di-filter semua
existing = list(webhook1)
hasil_filter = simulasi_filter_duplikat(existing, webhook2)
cek("Webhook 2x persis sama -> semua difilter (0 baris baru)",
    len(hasil_filter) == 0,
    "baris lolos filter: %d" % len(hasil_filter))

# Webhook ketiga dengan 1 pasien baru (koreksi, bukan duplikat)
webhook3 = webhook1 + [{'tanggal': '29/04/2026', 'sesi': 'Sesi III', 'nama': 'Budi Baru', 'jam': '09:00'}]
hasil_filter3 = simulasi_filter_duplikat(existing, webhook3)
cek("Webhook dengan 1 pasien baru -> hanya 1 baris baru yang lolos",
    len(hasil_filter3) == 1,
    "baris lolos: %d (seharusnya 1)" % len(hasil_filter3))
cek("Baris yang lolos adalah pasien baru",
    hasil_filter3[0]['nama'] == 'Budi Baru' if hasil_filter3 else False)

# Tanggal berbeda tidak terdampak filter
webhook_beda_tgl = [
    {'tanggal': '30/04/2026', 'sesi': 'Sesi I', 'nama': 'M. Rayhan', 'jam': '08:00'},
]
hasil_beda = simulasi_filter_duplikat(existing, webhook_beda_tgl)
cek("Tanggal berbeda tidak ikut terfilter",
    len(hasil_beda) == 1,
    "baris lolos: %d (seharusnya 1)" % len(hasil_beda))

# ══════════════════════════════════════════════════════════
# SKENARIO 13: Error notification — format pesan error
# ══════════════════════════════════════════════════════════
header("SKENARIO 13: Error notification ke BLAST_QUEUE")
print("  Ketika assignment gagal, pesan error harus masuk BLAST_QUEUE")
print()

from datetime import datetime, timezone, timedelta
WITA = timezone(timedelta(hours=8))

def buat_pesan_error(error_msg):
    ts = datetime.now(WITA).strftime("%d/%m/%Y %H:%M:%S")
    return (
        "GAGAL ASSIGNMENT\n"
        "Error: %s\n"
        "Waktu: %s\n"
        "Cek log Railway untuk detail." % (error_msg, ts)
    )

pesan = buat_pesan_error("Google Sheets API quota exceeded")
cek("Pesan error mengandung 'GAGAL ASSIGNMENT'",
    "GAGAL ASSIGNMENT" in pesan)
cek("Pesan error mengandung detail error",
    "Google Sheets API quota exceeded" in pesan)
cek("Pesan error mengandung timestamp",
    datetime.now(WITA).strftime("%d/%m/%Y") in pesan)

# ══════════════════════════════════════════════════════════
# SKENARIO 14: Timing konsisten — jam assignment
# ══════════════════════════════════════════════════════════
header("SKENARIO 14: Timing konsisten di response webhook")
print("  Response webhook harus bilang '10:00 WITA', bukan '23:00'")
print()

with open("app.py", encoding="utf-8") as f:
    app_content = f.read()

cek("Response webhook menyebut '10:00 WITA' (bukan '23:00')",
    "10:00 WITA" in app_content and "23:00" not in app_content)
cek("Route /process-input didefinisikan sebelum if __main__",
    app_content.index("@app.route('/process-input'") < app_content.index("if __name__"))
cek("Route /rebuild-rekap didefinisikan sebelum if __main__",
    app_content.index("@app.route('/rebuild-rekap'") < app_content.index("if __name__"))
cek("Thread menggunakan run_with_notif (ada error handling)",
    "run_with_notif" in app_content)
cek("filter_duplikat dipanggil di webhook",
    "filter_duplikat" in app_content)

print()
print("=" * 60)
print("  HASIL: %d PASS, %d FAIL" % (PASS, FAIL))
print("=" * 60)
if FAIL == 0:
    print("  Semua skenario berhasil.")
else:
    print("  Ada %d skenario yang gagal, periksa output di atas." % FAIL)
