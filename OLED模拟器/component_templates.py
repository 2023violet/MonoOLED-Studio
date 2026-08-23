from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path


class TemplateLibrary:
    def __init__(self, path: str | Path):
        self.path=Path(path)
        if self.path.exists():
            self.data=json.loads(self.path.read_text(encoding='utf-8'))
        else:
            self.data={'schema_version':1,'templates':{}}

    def names(self)->list[str]:
        return sorted(self.data.get('templates',{}))

    def save(self)->Path:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.path.write_text(json.dumps(self.data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return self.path

    def save_template(self,name:str,elements:list[dict])->None:
        if not name.strip(): raise ValueError('template name must not be empty')
        if not elements: raise ValueError('template must contain at least one element')
        self.data.setdefault('templates',{})[name]=deepcopy(elements)
        self.save()

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
