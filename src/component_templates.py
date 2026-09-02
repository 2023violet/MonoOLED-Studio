from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from atomic_io import atomic_write_bytes, atomic_write_json


class TemplateLibrary:
    def __init__(self, path: str | Path):
        self.path=Path(path)
        self.data={'schema_version':1,'templates':{}}
        if not self.path.exists():
            return
        try:
            raw=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(raw,dict) or int(raw.get('schema_version',1)) != 1 or not isinstance(raw.get('templates',{}),dict):
                raise ValueError('invalid template library structure')
            self.data=raw
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
            self._quarantine_corrupt()

    def _quarantine_corrupt(self) -> None:
        try:
            raw=self.path.read_bytes()
            quarantine=self.path.parent/'quarantine'; quarantine.mkdir(parents=True,exist_ok=True)
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
            atomic_write_bytes(quarantine/f'templates.corrupt.{stamp}.json',raw)
        except OSError:
            pass

    def names(self)->list[str]:
        return sorted(self.data.get('templates',{}))

    def save(self)->Path:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        atomic_write_json(self.path,self.data)
        return self.path

    def save_template(self,name:str,elements:list[dict])->None:
        if not name.strip(): raise ValueError('template name must not be empty')
        if not elements: raise ValueError('template must contain at least one element')
        before=deepcopy(self.data)
        self.data.setdefault('templates',{})[name]=deepcopy(elements)
        try:
            self.save()
        except OSError:
            self.data=before
            raise

    def instantiate(self,name:str,*,prefix:str='',offset:tuple[int,int]=(0,0))->list[dict]:
        try: src=self.data['templates'][name]
        except KeyError as exc: raise KeyError(f'unknown template: {name}') from exc
        dx,dy=map(int,offset)
        out=[]
        for item in deepcopy(src):
            item['id']=prefix+str(item['id'])
            if 'x' in item: item['x']=int(item['x'])+dx
            if 'y' in item: item['y']=int(item['y'])+dy
            if isinstance(item.get('zone'),dict):
                if 'x' in item['zone']: item['zone']['x']=int(item['zone']['x'])+dx
                if 'y' in item['zone']: item['zone']['y']=int(item['zone']['y'])+dy
            out.append(item)
        return out
