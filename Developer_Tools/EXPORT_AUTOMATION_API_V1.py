#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'OLED模拟器'
sys.path.insert(0,str(SIM))
from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS


def export_contract(target: Path | None=None) -> Path:
    target=target or (SIM/'AUTOMATION_API_V1.json')
    payload={
        'product':'MonoOLED Studio',
        'api':'Automation API',
        'api_version':AUTOMATION_API_VERSION,
        'transport':'semantic service; localhost token-authenticated JSON-RPC adapter',
        'methods':{name:METHOD_SPECS[name] for name in sorted(METHOD_SPECS)},
        'invariants':[
            'Automation manipulates project/scene/pixel/font semantics, never GUI coordinates.',
            'Canonical Renderer and Studio Exporter remain the pixel/export truth.',
            'Revision guards prevent stale writes.',
            'Scene/layout/selection/state-schema transactions can commit or rollback as one Designer history operation.',
            'State schema supports explicit discrete domains and constrained state-variable relations without script evaluation.',
            'Project, asset and pixel lifecycle operations are explicit and are not falsely advertised as scene-transaction rollback.',
        ],
    }
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=False)+'\n',encoding='utf-8')
    return target

if __name__=='__main__':
    p=export_contract(); print(p); raise SystemExit(0)
