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
