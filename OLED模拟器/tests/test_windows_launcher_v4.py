from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def test_delivery_has_single_top_level_windows_pe_launcher_with_robust_runtime_search_contract():
    exe=ROOT/'MonoOLEDStudio.exe'
    assert exe.exists()
    raw=exe.read_bytes()
    assert raw[:2]==b'MZ'
    assert b'PE\x00\x00' in raw[:2048]
    for text in ['pythonw.exe','.venv-runtime','ProgramFiles','LOCALAPPDATA','CuringLite.project.oled.json','gui.py']:
        assert text.encode('utf-16le') in raw, text
    assert b'#!pythonw.exe' not in raw


def test_launcher_selects_a_runtime_that_can_import_qt_before_launching_gui():
    raw=(ROOT/'MonoOLEDStudio.exe').read_bytes()
    for text in ['python.exe','PySide6','PIL','WaitForSingleObject','GetExitCodeProcess']:
        assert text.encode('utf-16le') in raw or text.encode('ascii') in raw, text


def test_launcher_uses_normal_windows_import_table_instead_of_peb_api_walking():
    raw=(ROOT/'MonoOLEDStudio.exe').read_bytes()
    assert b'KERNEL32.dll' in raw
    assert b'USER32.dll' in raw
    pe=raw.find(b'PE\x00\x00')
    opt=pe+24
    import_rva=int.from_bytes(raw[opt+0x78:opt+0x7c], 'little')
    import_size=int.from_bytes(raw[opt+0x7c:opt+0x80], 'little')
    assert import_rva != 0 and import_size >= 40
