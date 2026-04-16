"""
test_lokal.py — Test parser dan koneksi sheets tanpa harus deploy dulu
Jalankan: python test_lokal.py
"""

import sys
import logging
from parser_jadwal import parse_jadwal

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# ─── Pesan WA contoh ──────────────────────────────────────
PESAN_WA = """DAFTAR KEHADIRAN ANAK DI KLINIK TUMBUH KEMBANG - RSPB
Hari Senin, 13 April 2026
🌸 CATATAN 🌸
*Untuk kelancaran proses terapi kami mengharapkan kerja sama dari orang tua, apabila orang tua sdh mengisi daftar hadir d harapkan berkomitmen dan hadir tepat waktu, jika berhalangan hadir wajib konfirmasi d grup.**
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
☀️ *Sesi IV Jam 10.00
1. M. Akbar Alghazi
2. Al fath
3. M. Nafi
☀️ *Sesi V Jam 10.30
1. Jimi Ibrahim
2. Dafandra
3. M. Abdullah Zafier
4. Yusuf Khalid
☀️ *Sesi VI Jam 11.00
1. Arshaka keenandra
2. M. Arkanza
3. Alphonso van knoop
☀️ *Sesi VII Jam 14.00
1. Ibni Abbad
2. Shavina Sinta
3. Safaraz Ammar
4. Anugerah
☀️ *Sesi VIII Jam 14.30
1. Almira Hafizah
2. Rasydan Rauf
3. Bilal Alhanan
☀️ *Sesi IX Jam 15.00
1. Khalifah Hanan
2. Elshanum
3. Rayyis Dzawin
Terima kasih🙏🙏"""


def test_parser():
    print("\n" + "="*55)
    print("  TEST PARSER")
    print("="*55)

    hasil = parse_jadwal(PESAN_WA)

    print(f"\nTotal entri: {len(hasil)}")
    print(f"\n{'Sesi':<12} {'Jam':<7} {'No':<4} {'Nama'}")
    print("-"*55)

    for r in hasil:
        print(f"{r['sesi']:<12} {r['jam']:<7} {r['no']:<4} {r['nama']}")

    # Validasi
    assert len(hasil) == 32, f"Ekspektasi 32 baris, dapat {len(hasil)}"
    assert hasil[0]['nama']  == 'Grace Zefanya',    f"Baris 1 salah: {hasil[0]['nama']}"
    assert hasil[-1]['nama'] == 'Rayyis Dzawin',    f"Baris terakhir salah: {hasil[-1]['nama']}"
    assert hasil[11]['nama'] == 'Xyena',            f"Xyena harusnya bersih dari '9.30)': {hasil[11]['nama']}"
    assert hasil[29]['sesi'] == 'Sesi IX',          f"Sesi IX salah terbaca: {hasil[29]['sesi']}"

    print("\n✓ Semua validasi parser PASSED")
    return True


def test_sheets():
    print("\n" + "="*55)
    print("  TEST KONEKSI GOOGLE SHEETS")
    print("="*55)

    try:
        from dotenv import load_dotenv
        load_dotenv()

        from sheets_client import SheetsClient
        client = SheetsClient()
        print("✓ Koneksi ke Google Sheets berhasil")

        # Test simpan 2 baris dummy
        test_rows = [
            {
                'timestamp': '2026-04-13 08:00:00',
                'tanggal':   '13/04/2026',
                'sesi':      'Sesi TEST',
                'jam':       '08:00',
                'no':        1,
                'nama':      'TEST DUMMY — HAPUS'
            }
        ]
        saved = client.append_rows(test_rows)
        print(f"✓ Berhasil simpan {saved} baris dummy ke sheet")
        print("  ⚠️  Hapus baris dummy 'TEST DUMMY — HAPUS' dari sheet secara manual")
        return True

    except ImportError:
        print("⚠️  dotenv/gspread belum terinstall. Jalankan: pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"✗ Koneksi Sheets gagal: {e}")
        print("  Pastikan .env sudah diisi dan service_account.json ada di folder credentials/")
        return False


def test_full_flow():
    print("\n" + "="*55)
    print("  TEST FULL FLOW (parser + sheets)")
    print("="*55)

    try:
        from dotenv import load_dotenv
        load_dotenv()
        from sheets_client import SheetsClient

        hasil = parse_jadwal(PESAN_WA)
        client = SheetsClient()
        saved = client.append_rows(hasil)

        print(f"✓ Full flow berhasil: {saved} baris tersimpan ke Google Sheets")
        return True

    except Exception as e:
        print(f"✗ Full flow gagal: {e}")
        return False


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'parser'

    if mode == 'parser':
        test_parser()
    elif mode == 'sheets':
        test_sheets()
    elif mode == 'full':
        test_parser()
        test_full_flow()
    else:
        print("Usage: python test_lokal.py [parser|sheets|full]")
