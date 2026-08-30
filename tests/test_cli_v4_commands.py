import sys
from pathlib import Path
SIM=Path(__file__).resolve().parents[1] / 'src'; ROOT=SIM.parent; sys.path.insert(0,str(SIM))
from cli import build_parser, main


def test_cli_exposes_v4_project_batch_handoff_asset_and_c_header_commands(tmp_path):
    parser=build_parser()
    for argv in [
        ['batch-validate','--scene','main_scene','--output',str(tmp_path/'batch.md')],
        ['handoff','--scene','main_scene','--output',str(tmp_path/'handoff.zip')],
        ['asset-audit','--project',str(ROOT/'test_assets/projects/curing_lite/project.oled.json')],
        ['c-header','--scene','main_scene','--output',str(tmp_path/'frame.h')],
    ]:
        args=parser.parse_args(argv)
        assert callable(args.func)


def test_cli_batch_validate_and_c_header_execute(tmp_path):
    assert main(['batch-validate','--scene','main_scene','--output',str(tmp_path/'batch.md')])==0
    assert (tmp_path/'batch.md').exists()
    assert main(['c-header','--scene','main_scene','--output',str(tmp_path/'frame.h')])==0
    assert 'uint8_t' in (tmp_path/'frame.h').read_text(encoding='utf-8')
