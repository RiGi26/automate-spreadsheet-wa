"""
parser_jadwal.py — Ekstrak data jadwal dari pesan WhatsApp klinik
"""

import re
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# Peta nama bulan Indonesia → nomor bulan
BULAN_ID = {
    'januari': 1, 'februari': 2, 'maret': 3, 'april': 4,
    'mei': 5, 'juni': 6, 'juli': 7, 'agustus': 8,
    'september': 9, 'oktober': 10, 'november': 11, 'desember': 12
}

# Semua kemungkinan sesi (I sampai XII)
# PENTING: urutan dari paling panjang ke pendek supaya IX tidak match sebagai I
POLA_SESI = re.compile(
    r'Sesi\s+(XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)',
    re.IGNORECASE
)
POLA_JAM   = re.compile(r'Jam\s+(\d{1,2}[.:]\d{2})', re.IGNORECASE)
POLA_TGL   = re.compile(r'(\d{1,2})\s+(\w+)\s+(\d{4})')
POLA_ITEM  = re.compile(r'^(\d+)\.\s+(.+)')
POLA_WAKTU = re.compile(r'\s*\(?\d{1,2}[.:]\d{2}\)?\s*$')  # hapus jam di akhir nama

# Karakter dekorasi WA yang perlu dibersihkan
EMOJI_DAN_FORMAT = re.compile(
    r'[*_~`]|'         # markdown WA
    r'[\U0001F300-\U0001FFFF]|'  # emoji umum
    r'[\u2600-\u26FF]|'  # misc symbols (☀️🌸)
    r'[\u2700-\u27BF]'   # dingbats
)


def bersihkan_pesan(text: str) -> str:
    """Bersihkan formatting WA, emoji, dan normalisasi newline."""
    text = text.replace('\\n', '\n').replace('%0A', '\n').replace('%0D', '\r')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = EMOJI_DAN_FORMAT.sub('', text)
    return text


def parse_tanggal(text: str) -> str:
    """
    Ekstrak dan format tanggal dari teks.
    Contoh: '13 April 2026' → '13/04/2026'
    """
    m = POLA_TGL.search(text)
    if not m:
        return datetime.today().strftime('%d/%m/%Y')

    tgl_str, bln_str, thn_str = m.group(1), m.group(2).lower(), m.group(3)
    bulan = BULAN_ID.get(bln_str)

    if not bulan:
        log.warning(f"Nama bulan tidak dikenali: {bln_str}")
        return datetime.today().strftime('%d/%m/%Y')

    return f"{int(tgl_str):02d}/{bulan:02d}/{thn_str}"


def parse_jadwal(text: str) -> list[dict]:
    """
    Parse pesan jadwal WA menjadi list dict.

    Returns:
        List of dict: [
            {
                'timestamp': '2026-04-13 08:00:00',
                'tanggal':   '13/04/2026',
                'sesi':      'Sesi I',
                'jam':       '08:00',
                'no':        1,
                'nama':      'Grace Zefanya'
            },
            ...
        ]
    """
    text_bersih = bersihkan_pesan(text)
    tanggal     = parse_tanggal(text_bersih)
    timestamp   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    lines = [l.strip() for l in text_bersih.split('\n') if l.strip()]

    rows      = []
    sesi      = ''
    jam       = ''
    no_urut   = {}   # counter per sesi

    # Flag: mulai proses hanya setelah sesi pertama terdeteksi
    # supaya baris CATATAN tidak ikut terparse
    sesi_mulai = False

    for line in lines:
        # Cek apakah baris ini header sesi
        m_sesi = POLA_SESI.search(line)
        m_jam  = POLA_JAM.search(line)

        if m_sesi:
            sesi       = f"Sesi {m_sesi.group(1).upper()}"
            sesi_mulai = True
            if sesi not in no_urut:
                no_urut[sesi] = 0
            log.debug(f"Sesi terdeteksi: {sesi}")

        if m_jam:
            jam = m_jam.group(1).replace('.', ':')
            log.debug(f"Jam terdeteksi: {jam}")

        # Skip baris sebelum sesi pertama (bagian CATATAN)
        if not sesi_mulai:
            continue

        # Cek apakah baris ini entry nama pasien: "1. Nama Pasien"
        m_item = POLA_ITEM.match(line)
        if m_item and sesi:
            nama = m_item.group(2).strip()

            # Bersihkan sisa jam di akhir nama, misal "Xyena 9.30)"
            nama = POLA_WAKTU.sub('', nama).strip()

            # Bersihkan karakter non-printable
            nama = re.sub(r'[^\w\s.\-]', '', nama).strip()

            if not nama:
                continue

            no_urut[sesi] = no_urut.get(sesi, 0) + 1

            rows.append({
                'timestamp': timestamp,
                'tanggal':   tanggal,
                'sesi':      sesi,
                'jam':       jam,
                'no':        no_urut[sesi],
                'nama':      nama
            })
            log.debug(f"  [{sesi}] {no_urut[sesi]}. {nama}")

    log.info(f"Total parse: {len(rows)} entri dari {len(no_urut)} sesi")
    return rows


# ─── Test manual ──────────────────────────────────────────
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    CONTOH = """DAFTAR KEHADIRAN ANAK DI KLINIK TUMBUH KEMBANG - RSPB
Hari Senin, 13 April 2026

🌸 CATATAN 🌸
*Untuk kelancaran proses terapi kami mengharapkan kerja sama dari orang tua*

☀️ *Sesi I Jam 08.00
1. Grace Zefanya
2. Nabil Arsyad
3. Raffasya Arkana
☀️ *Sesi II Jam 08.30
1. Kenneth Athallah
2. Khaula Zia
3. Numa
4. M. Yusan
☀️ *Sesi III Jam 09.00
1. Azzam Abdullah l
2. Chairil Rafqi
3. Rajh
4. Felicia
5. Xyena 9.30)
☀️ *Sesi IX Jam 15.00
1. Khalifah Hanan
2. Elshanum
3. Rayyis Dzawin"""

    hasil = parse_jadwal(CONTOH)
    print(f"\nTotal: {len(hasil)} baris\n")
    for r in hasil:
        print(f"  {r['sesi']:10s} | {r['jam']:5s} | {r['no']}. {r['nama']}")
