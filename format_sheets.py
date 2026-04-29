import sys
sys.path.insert(0, '/home/rigizaf26/automate-spreadsheet-wa')
from dotenv import load_dotenv
load_dotenv('/home/rigizaf26/automate-spreadsheet-wa/.env')
from sheets_client import SheetsClient

sc = SheetsClient()
ss = sc._client.open_by_key('1GaAeD3fFSrZAARDB2tKsRaXr79FhtSEfQUmYg6_Z1io')

# Warna tema
BIRU_TUA    = {'red': 0.129, 'green': 0.263, 'blue': 0.529}
BIRU_MUDA   = {'red': 0.235, 'green': 0.447, 'blue': 0.733}
HIJAU_TUA   = {'red': 0.133, 'green': 0.408, 'blue': 0.208}
PUTIH       = {'red': 1.0,   'green': 1.0,   'blue': 1.0}
ABU_TERANG  = {'red': 0.937, 'green': 0.945, 'blue': 0.961}
ABU_BORDER  = {'red': 0.780, 'green': 0.800, 'blue': 0.835}

def col_letter(n):
    result = ''
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result

def get_max_col(data):
    """Cari kolom terakhir yang ada isinya"""
    max_col = 0
    for row in data:
        for i, cell in enumerate(row):
            if str(cell).strip():
                if i + 1 > max_col:
                    max_col = i + 1
    return max_col

def format_sheet(name, header_color, freeze_cols=0):
    try:
        ws   = ss.worksheet(name)
        data = ws.get_all_values()
        if not data:
            print(f'Skip {name} — kosong')
            return

        n_rows   = len(data)
        max_col  = get_max_col(data)

        if max_col == 0:
            print(f'Skip {name} — tidak ada data')
            return

        print(f'Format {name}: {n_rows} baris, {max_col} kolom aktif')

        ws_id = ws.id
        requests = []

        # 1. Reset background seluruh sheet jadi putih dulu
        requests.append({
            'repeatCell': {
                'range': {'sheetId': ws_id},
                'cell': {'userEnteredFormat': {'backgroundColor': PUTIH}},
                'fields': 'userEnteredFormat.backgroundColor'
            }
        })

        # 2. Format header hanya sampai max_col
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': ws_id,
                    'startRowIndex': 0,
                    'endRowIndex': 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': max_col
                },
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': header_color,
                        'textFormat': {
                            'foregroundColor': PUTIH,
                            'bold': True,
                            'fontSize': 10
                        },
                        'horizontalAlignment': 'CENTER',
                        'verticalAlignment': 'MIDDLE'
                    }
                },
                'fields': 'userEnteredFormat'
            }
        })

        # 3. Zebra stripe baris genap
        for i in range(2, n_rows + 1, 2):
            requests.append({
                'repeatCell': {
                    'range': {
                        'sheetId': ws_id,
                        'startRowIndex': i - 1,
                        'endRowIndex': i,
                        'startColumnIndex': 0,
                        'endColumnIndex': max_col
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': ABU_TERANG
                        }
                    },
                    'fields': 'userEnteredFormat.backgroundColor'
                }
            })

        # 4. Border seluruh data
        border_style = {'style': 'SOLID', 'color': ABU_BORDER}
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': ws_id,
                    'startRowIndex': 0,
                    'endRowIndex': n_rows,
                    'startColumnIndex': 0,
                    'endColumnIndex': max_col
                },
                'cell': {
                    'userEnteredFormat': {
                        'borders': {
                            'top':    border_style,
                            'bottom': border_style,
                            'left':   border_style,
                            'right':  border_style
                        },
                        'textFormat': {'fontSize': 9},
                        'verticalAlignment': 'MIDDLE'
                    }
                },
                'fields': 'userEnteredFormat.borders,userEnteredFormat.textFormat,userEnteredFormat.verticalAlignment'
            }
        })

        # 5. Autofit kolom
        requests.append({
            'autoResizeDimensions': {
                'dimensions': {
                    'sheetId': ws_id,
                    'dimension': 'COLUMNS',
                    'startIndex': 0,
                    'endIndex': max_col
                }
            }
        })

        # 6. Freeze
        requests.append({
            'updateSheetProperties': {
                'properties': {
                    'sheetId': ws_id,
                    'gridProperties': {
                        'frozenRowCount': 1,
                        'frozenColumnCount': freeze_cols
                    }
                },
                'fields': 'gridProperties.frozenRowCount,gridProperties.frozenColumnCount'
            }
        })

        # Jalankan semua request sekaligus
        ss.batch_update({'requests': requests})
        print(f'✅ {name} selesai')

    except Exception as e:
        print(f'❌ Error {name}: {e}')

# Format tiap sheet
format_sheet('Jadwal',       BIRU_TUA,   freeze_cols=0)
format_sheet('PASIEN',       BIRU_MUDA,  freeze_cols=2)
format_sheet('RIWAYAT',      BIRU_TUA,   freeze_cols=2)
format_sheet('TERAPIS',      HIJAU_TUA,  freeze_cols=0)
format_sheet('CUTI',         HIJAU_TUA,  freeze_cols=0)
format_sheet('BLAST_QUEUE',  BIRU_MUDA,  freeze_cols=0)
format_sheet('REKAP_PASIEN', BIRU_TUA,   freeze_cols=2)

print('\nSemua sheet selesai diformat!')
