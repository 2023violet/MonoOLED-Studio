from pathlib import Path
import sys

SIM=Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0,str(SIM))
from batch_validate import build_state_matrix, validate_matrix


def test_state_matrix_covers_enum_and_integer_boundaries():
    scene={'canvas':{'w':32,'h':16},'storage':{'bytes_per_frame':64},'states':{
      'mode':{'type':'enum','values':['A','B'],'init':'A'},
      'phase':{'type':'enum','values':['standby','running'],'init':'standby'},
      'battery':{'type':'int','min':0,'max':4,'init':4},
      'seconds':{'type':'int','min':0,'max':10,'init':5}},'elements':[],'timeline':[]}
    matrix=build_state_matrix(scene, integer_policy='boundaries')
    assert len(matrix)==2*2*3*3
    summary=validate_matrix(scene,matrix)
    assert summary.cases==36 and summary.blockers==0


def test_matrix_validation_reuses_resource_decoding_across_cases(tmp_path, monkeypatch):
    from PIL import Image
    import assets
    import resource_cache

    asset_path = tmp_path / 'icon.png'
    Image.new('1', (2, 2), 1).save(asset_path)
    scene = {
        '_root': str(tmp_path),
        'canvas': {'w': 8, 'h': 8},
        'storage': {'bytes_per_frame': 8},
        'states': {},
        'elements': [{'id': 'icon', 'type': 'image', 'asset': 'icon.png', 'x': 1, 'y': 2, 'w': 2, 'h': 2}],
        'timeline': [],
    }
    decode = assets.decode_bitmap_bytes
    decoded_paths = []

    def track_decode(path, raw):
        decoded_paths.append(Path(path).resolve())
        return decode(path, raw)

    monkeypatch.setattr(assets, 'decode_bitmap_bytes', track_decode)
    monkeypatch.setattr(resource_cache, 'decode_bitmap_bytes', track_decode)

    summary = validate_matrix(scene, [{}, {}])

    assert summary.blockers == 0
    assert decoded_paths == [asset_path.resolve()]
