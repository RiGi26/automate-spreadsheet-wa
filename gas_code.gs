// ═══════════════════════════════════════════════════════════════
// KONSTANTA — sesuaikan jika perlu
// ═══════════════════════════════════════════════════════════════
const SPREADSHEET_ID  = '1GaAeD3fFSrZAARDB2tKsRaXr79FhtSEfQUmYg6_Z1io';
const FONNTE_TOKEN    = 'ixYH1t8TjSVKpLnDn8C4';
const GRUP_BLAST_ID   = '120363046770073794@g.us';
const RAILWAY_URL     = 'https://web-production-177cc.up.railway.app';

const GRUP_ABSENSI_A  = '120363046710189034@g.us';
const GRUP_ABSENSI_B  = '';   // kosongkan string jika hanya 1 grup


// ═══════════════════════════════════════════════════════════════
// WEBHOOK RECEIVER — dipanggil Fonnte saat ada pesan masuk
// ═══════════════════════════════════════════════════════════════

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    const message = String(payload.message || payload.pesan || payload.text || '');
    let   isGroup = payload.isgroup || payload.isGroup || payload.is_group || false;
    const sender  = String(payload.sender || payload.from || '');

    if (typeof isGroup === 'string') {
      isGroup = ['true', '1', 'yes'].includes(isGroup.toLowerCase());
    }

    if (!isGroup)
      return _jsonResp('ignored', 'bukan grup');

    const grupAbsensi = [GRUP_ABSENSI_A, GRUP_ABSENSI_B].filter(Boolean);
    if (!grupAbsensi.includes(sender))
      return _jsonResp('ignored', 'bukan grup absensi');

    if (!message.toUpperCase().includes('DAFTAR KEHADIRAN ANAK'))
      return _jsonResp('ignored', 'bukan pesan target');

    const rows = parseJadwal(message);
    if (!rows.length)
      return _jsonResp('error', 'parse gagal - tidak ada data');

    const ss       = SpreadsheetApp.openById(SPREADSHEET_ID);
    const wsJadwal = ss.getSheetByName('Jadwal');
    if (!wsJadwal)
      return _jsonResp('error', 'sheet Jadwal tidak ditemukan');

    const rowsBaru = filterDuplikatJadwal(wsJadwal, rows);
    if (!rowsBaru.length)
      return _jsonResp('ignored', 'duplikat - data sudah ada');

    const toSave = rowsBaru.map(r => [r.timestamp, r.tanggal, r.sesi, r.jam, r.no, r.nama, r.status]);
    wsJadwal.getRange(wsJadwal.getLastRow() + 1, 1, toSave.length, 7).setValues(toSave);

    Logger.log(`doPost: ${toSave.length} baris disimpan dari ${sender}`);
    return _jsonResp('ok', `${toSave.length} baris disimpan, assign otomatis jam 22:00 WITA`);

  } catch (err) {
    Logger.log('doPost error: ' + err.toString());
    return _jsonResp('error', err.toString());
  }
}

function _jsonResp(status, reason) {
  return ContentService
    .createTextOutput(JSON.stringify({ status: status, reason: reason }))
    .setMimeType(ContentService.MimeType.JSON);
}


// ═══════════════════════════════════════════════════════════════
// PARSER JADWAL — port dari parser_jadwal.py
// ═══════════════════════════════════════════════════════════════

const _BULAN_ID = {
  januari:1, februari:2, maret:3, april:4, mei:5, juni:6,
  juli:7, agustus:8, september:9, oktober:10, november:11, desember:12
};
const _BLACKLIST = ['grup a', 'grup b', 'grup c', 'grup d', '-', 'kosong', 'libur'];

function _bersihkanPesan(text) {
  text = text.replace(/\\n/g, '\n').replace(/%0A/g, '\n').replace(/%0D/g, '\r');
  text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  text = text.replace(/[*_~`]/g, '');
  text = text.replace(/[​-‏⁠⁡﻿ ‎‍‌]/g, '');
  return text;
}

function _parseTanggal(text) {
  const m = text.match(/(\d{1,2})\s+(\w+)\s+(\d{4})/);
  if (!m) return Utilities.formatDate(new Date(), 'Asia/Makassar', 'dd/MM/yyyy');
  const bulan = _BULAN_ID[m[2].toLowerCase()];
  if (!bulan) return Utilities.formatDate(new Date(), 'Asia/Makassar', 'dd/MM/yyyy');
  return String(m[1]).padStart(2, '0') + '/' + String(bulan).padStart(2, '0') + '/' + m[3];
}

function parseJadwal(text) {
  const POLA_SESI  = /Sesi\s+(XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)/i;
  const POLA_JAM   = /Jam\s+(\d{1,2}[.:]\d{2})/i;
  const POLA_ITEM  = /^(\d+)\.\s+(.+)/;
  const POLA_WAKTU = /\s*\(?\d{1,2}[.:]\d{2}\)?\s*$/;

  const textBersih = _bersihkanPesan(text);
  const tanggal    = _parseTanggal(textBersih);
  const timestamp  = Utilities.formatDate(new Date(), 'Asia/Makassar', 'dd/MM/yyyy HH:mm:ss');
  const lines      = textBersih.split('\n').map(l => l.trim()).filter(l => l);

  const rows    = [];
  let sesi      = '';
  let jam       = '';
  let sesiMulai = false;
  const noUrut  = {};

  for (let line of lines) {
    line = line.replace(/^[​-‏⁠⁡﻿ ‎‍‌]+/, '');

    const mSesi = line.match(POLA_SESI);
    const mJam  = line.match(POLA_JAM);

    if (mSesi) {
      sesi      = 'Sesi ' + mSesi[1].toUpperCase();
      sesiMulai = true;
      if (!(sesi in noUrut)) noUrut[sesi] = 0;
    }
    if (mJam) {
      jam = mJam[1].replace('.', ':');
    }
    if (!sesiMulai) continue;

    const mItem = line.match(POLA_ITEM);
    if (mItem && sesi) {
      let nama = mItem[2].trim();
      nama = nama.replace(POLA_WAKTU, '').trim();
      nama = nama.replace(/[^\w\s.\-]/g, '').trim();

      if (!nama || _BLACKLIST.includes(nama.toLowerCase())) continue;

      noUrut[sesi] = (noUrut[sesi] || 0) + 1;
      rows.push({ timestamp, tanggal, sesi, jam, no: noUrut[sesi], nama, status: 'PENDING' });
    }
  }

  Logger.log('parseJadwal: ' + rows.length + ' entri dari ' + Object.keys(noUrut).length + ' sesi');
  return rows;
}

function filterDuplikatJadwal(wsJadwal, rows) {
  const existing    = wsJadwal.getDataRange().getValues();
  const existingSet = new Set();

  // kolom sheet Jadwal: 0=timestamp, 1=tanggal, 2=sesi, 3=jam, 4=no, 5=nama, 6=status
  for (let i = 1; i < existing.length; i++) {
    const key = (String(existing[i][1]) + '|' + String(existing[i][2]) + '|' + String(existing[i][5])).toLowerCase();
    existingSet.add(key);
  }

  return rows.filter(r => {
    const key = (r.tanggal + '|' + r.sesi + '|' + r.nama).toLowerCase();
    return !existingSet.has(key);
  });
}


// ═══════════════════════════════════════════════════════════════
// BLAST QUEUE — kirim pesan WA dari antrian
// ═══════════════════════════════════════════════════════════════

function cekDanBlast() {
  const ss     = SpreadsheetApp.openById(SPREADSHEET_ID);
  const wsFifo = ss.getSheetByName('BLAST_QUEUE');
  if (!wsFifo) return;

  const data = wsFifo.getDataRange().getValues();
  if (data.length <= 1) return;

  for (let i = 1; i < data.length; i++) {
    const status = data[i][0];
    const pesan  = data[i][1];
    const target = data[i][3] || GRUP_BLAST_ID;

    if (status === 'PENDING' || status === 'FAILED') {
      const berhasil = kirimWA(pesan, target);
      wsFifo.getRange(i + 1, 1).setValue(berhasil ? 'SENT' : 'FAILED');
      wsFifo.getRange(i + 1, 3).setValue(new Date().toLocaleString('id-ID'));
      Utilities.sleep(1000);
    }
  }
  bersihkanQueue(wsFifo);
}

function kirimWA(pesan, target) {
  try {
    const url     = 'https://api.fonnte.com/send';
    const options = {
      method: 'post',
      headers: { 'Authorization': FONNTE_TOKEN },
      payload: { target: target, message: pesan, countryCode: '62' },
      muteHttpExceptions: true
    };
    const resp   = UrlFetchApp.fetch(url, options);
    const result = JSON.parse(resp.getContentText());
    return result.status === true;
  } catch (e) {
    Logger.log('Error kirimWA: ' + e.toString());
    return false;
  }
}

function bersihkanQueue(ws) {
  const data      = ws.getDataRange().getValues();
  const rowsKeep  = [data[0]];

  for (let i = 1; i < data.length; i++) {
    if (data[i][0] !== 'SENT') rowsKeep.push(data[i]);
  }

  ws.clearContents();
  ws.getRange(1, 1, rowsKeep.length, rowsKeep[0].length).setValues(rowsKeep);
}


// ═══════════════════════════════════════════════════════════════
// TRIGGER KE RAILWAY — process-input & rebuild-rekap
// ═══════════════════════════════════════════════════════════════

function triggerProcessInput() {
  const url     = RAILWAY_URL + '/process-input';
  const options = {
    method: 'post',
    headers: { 'X-Secret': 'rebuild123' },
    muteHttpExceptions: true
  };
  const resp   = UrlFetchApp.fetch(url, options);
  const result = JSON.parse(resp.getContentText());
  Logger.log('Process input response: ' + JSON.stringify(result));
}

function triggerRebuildRekap() {
  const url     = RAILWAY_URL + '/rebuild-rekap';
  const options = {
    method: 'post',
    headers: { 'X-Secret': 'rebuild123' },
    muteHttpExceptions: true
  };
  const resp = UrlFetchApp.fetch(url, options);
  Logger.log('Rebuild response: ' + resp.getContentText());
}

function cekInputJadwal() {
  const ss      = SpreadsheetApp.openById(SPREADSHEET_ID);
  const wsInput = ss.getSheetByName('INPUT_JADWAL');
  if (!wsInput) return;

  const data = wsInput.getDataRange().getValues();
  if (data.length <= 1) return;

  let adaProses = false;
  for (let i = 1; i < data.length; i++) {
    if (data[i][0] === 'PROSES') { adaProses = true; break; }
  }
  if (!adaProses) return;

  try {
    const url     = RAILWAY_URL + '/process-input';
    const options = {
      method: 'post',
      headers: { 'X-Secret': 'rebuild123' },
      muteHttpExceptions: true
    };
    const resp   = UrlFetchApp.fetch(url, options);
    const result = JSON.parse(resp.getContentText());
    Logger.log('Process input response: ' + JSON.stringify(result));

    if (result.status === 'ok') {
      for (let i = 1; i < data.length; i++) {
        if (data[i][0] === 'PROSES') wsInput.getRange(i + 1, 1).setValue('DONE');
      }
    }
  } catch (e) {
    Logger.log('Error cekInputJadwal: ' + e.toString());
  }
}


// ═══════════════════════════════════════════════════════════════
// REBUILD REKAP PASIEN — dari sheet RIWAYAT
// ═══════════════════════════════════════════════════════════════

function rebuildRekapPasien() {
  const ss        = SpreadsheetApp.openById(SPREADSHEET_ID);
  const wsRiwayat = ss.getSheetByName('RIWAYAT');
  if (!wsRiwayat) return;

  const riwayatData = wsRiwayat.getDataRange().getValues();
  if (riwayatData.length <= 1) return;

  const pasienMap = {};

  for (let i = 1; i < riwayatData.length; i++) {
    const row     = riwayatData[i];
    const tgl     = row[1];
    const nama    = String(row[2]).trim();
    const no_rm   = row[3];
    const terapis = row[6];

    if (!nama) continue;

    if (!pasienMap[nama]) pasienMap[nama] = { no_rm: no_rm, sesi_list: [] };
    pasienMap[nama].sesi_list.push({ tgl: tgl, terapis: terapis });
  }

  for (const nama in pasienMap) {
    pasienMap[nama].sesi_list.sort((a, b) => {
      const parseDate = d => {
        if (!d) return 0;
        const parts = d.toString().split('/');
        if (parts.length === 3) return new Date(parts[2], parts[1] - 1, parts[0]);
        return new Date(d);
      };
      return parseDate(a.tgl) - parseDate(b.tgl);
    });
  }

  let maxSesi = 0;
  for (const nama in pasienMap) {
    if (pasienMap[nama].sesi_list.length > maxSesi) maxSesi = pasienMap[nama].sesi_list.length;
  }

  const header = ['NAMA', 'NO_RM', 'TOTAL_SESI', 'TERAPIS_TERAKHIR'];
  for (let i = 1; i <= maxSesi; i++) {
    header.push('SESI_' + i + '_TGL');
    header.push('SESI_' + i + '_TERAPIS');
  }

  const outputRows = [header];
  for (const nama in pasienMap) {
    const data             = pasienMap[nama];
    const sesiList         = data.sesi_list;
    const terapisTerakhir  = sesiList.length > 0 ? sesiList[sesiList.length - 1].terapis : '';
    const row = [nama, data.no_rm, sesiList.length, terapisTerakhir];

    for (let i = 0; i < sesiList.length; i++) {
      row.push(sesiList[i].tgl);
      row.push(sesiList[i].terapis);
    }
    outputRows.push(row);
  }

  let wsRekap = ss.getSheetByName('REKAP_PASIEN');
  if (!wsRekap) wsRekap = ss.insertSheet('REKAP_PASIEN');

  wsRekap.clearContents();
  wsRekap.getRange(1, 1, outputRows.length, outputRows[0].length).setValues(outputRows);
  wsRekap.getRange(1, 1, 1, header.length)
    .setBackground('#4472C4').setFontColor('#FFFFFF').setFontWeight('bold');
  wsRekap.setFrozenRows(1);
  wsRekap.setFrozenColumns(2);

  Logger.log('REKAP_PASIEN rebuild selesai: ' + (outputRows.length - 1) + ' pasien');
}


// ═══════════════════════════════════════════════════════════════
// MENU & UI
// ═══════════════════════════════════════════════════════════════

function prosesJadwalManual() {
  const ui         = SpreadsheetApp.getUi();
  const konfirmasi = ui.alert(
    'Proses Assignment',
    'Proses semua baris yang belum di-assign di sheet Jadwal?',
    ui.ButtonSet.YES_NO
  );
  if (konfirmasi !== ui.Button.YES) return;

  try {
    const url     = RAILWAY_URL + '/process-input';
    const options = {
      method: 'post',
      headers: { 'X-Secret': 'rebuild123' },
      muteHttpExceptions: true
    };
    const resp   = UrlFetchApp.fetch(url, options);
    const result = JSON.parse(resp.getContentText());

    if (result.status === 'ok') {
      ui.alert('Berhasil!', 'Assignment sedang diproses. Cek sheet Jadwal dalam beberapa detik.', ui.ButtonSet.OK);
    } else {
      ui.alert('Gagal!', result.message, ui.ButtonSet.OK);
    }
  } catch (e) {
    ui.alert('Error', e.toString(), ui.ButtonSet.OK);
  }
}

function buatMenu() {
  SpreadsheetApp.getUi()
    .createMenu('🏥 Klinik')
    .addItem('▶ Proses Assignment Jadwal', 'prosesJadwalManual')
    .addItem('🔄 Rebuild Rekap Pasien', 'triggerRebuildRekap')
    .addToUi();
}

function onOpen() {
  buatMenu();
}


// ═══════════════════════════════════════════════════════════════
// SETUP TRIGGER — jalankan sekali untuk pasang semua trigger
// ═══════════════════════════════════════════════════════════════

function setupSemuaTrigger() {
  // Hapus semua trigger lama
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));

  // Blast queue: setiap 1 menit
  ScriptApp.newTrigger('cekDanBlast')
    .timeBased().everyMinutes(1).create();

  // Cek INPUT_JADWAL: setiap 1 menit
  ScriptApp.newTrigger('cekInputJadwal')
    .timeBased().everyMinutes(1).create();

  // Assignment otomatis: jam 22:00 WITA (= 14:00 UTC)
  ScriptApp.newTrigger('triggerProcessInput')
    .timeBased().atHour(14).everyDays(1).create();

  // Rebuild rekap: jam 00:00 WITA (= 16:00 UTC hari sebelumnya)
  ScriptApp.newTrigger('triggerRebuildRekap')
    .timeBased().atHour(16).everyDays(1).create();

  Logger.log('Semua trigger berhasil dipasang');
}


// ═══════════════════════════════════════════════════════════════
// DEBUGGING & TEST
// ═══════════════════════════════════════════════════════════════

function testDoPost() {
  const fakePayload = {
    message: `DAFTAR KEHADIRAN ANAK DI KLINIK TUMBUH KEMBANG - RSPB
Hari Senin, 19 Mei 2026

Sesi I Jam 08.00
1. Test Pasien
2. Anak Kedua

Sesi II Jam 08.30
1. Pasien Tiga`,
    isgroup: true,
    sender: GRUP_ABSENSI_A
  };

  const fakeEvent = { postData: { contents: JSON.stringify(fakePayload) } };
  const result    = doPost(fakeEvent);
  Logger.log('testDoPost result: ' + result.getContent());
}

function debugCek() {
  const ss     = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheets = ss.getSheets().map(s => s.getName());
  Logger.log('Sheets: ' + sheets);

  const ws = ss.getSheetByName('BLAST_QUEUE');
  if (!ws) { Logger.log('BLAST_QUEUE tidak ditemukan!'); return; }

  const data = ws.getDataRange().getValues();
  Logger.log('Total baris: ' + data.length);
  Logger.log('Baris 1: ' + data[0]);
  if (data.length > 1) Logger.log('Baris 2: ' + data[1]);
}

function testKirim() {
  const url     = 'https://api.fonnte.com/send';
  const options = {
    method: 'post',
    headers: { 'Authorization': FONNTE_TOKEN },
    payload: { target: '6281296917963', message: 'test blast dari GAS', countryCode: '62' },
    muteHttpExceptions: true
  };
  const resp = UrlFetchApp.fetch(url, options);
  Logger.log(resp.getContentText());
}

function getGroups() {
  const url     = 'https://api.fonnte.com/get-whatsapp-group';
  const options = { method: 'post', headers: { 'Authorization': FONNTE_TOKEN }, muteHttpExceptions: true };
  const resp    = UrlFetchApp.fetch(url, options);
  Logger.log(resp.getContentText());
}

function testKirimGrup() {
  const url     = 'https://api.fonnte.com/send';
  const options = {
    method: 'post',
    headers: { 'Authorization': FONNTE_TOKEN },
    payload: { target: '120363429034634571@g.us', message: 'test blast ke grup Testing Project', countryCode: '62' },
    muteHttpExceptions: true
  };
  const resp = UrlFetchApp.fetch(url, options);
  Logger.log(resp.getContentText());
}
