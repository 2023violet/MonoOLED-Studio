from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Iterable

LATENCY_BUDGET_MS={
    'button_feedback':16.0,
    'popup_open':32.0,
    'popup_select_close':50.0,
    'tab_switch':50.0,
    'language_switch':100.0,
    'theme_switch':120.0,
    'density_switch':120.0,
    'ui_scale_switch':150.0,
    'inspector_edit':50.0,
}

def percentile(values:Iterable[float],q:float)->float:
    data=sorted(float(v) for v in values)
    if not data:return 0.0
    q=max(0.0,min(1.0,float(q)));idx=max(0,min(len(data)-1,math.ceil(q*len(data))-1));return data[idx]

@dataclass
class UiLatencyProfiler:
    samples:dict[str,list[float]]=field(default_factory=dict)
    max_samples:int=512
    def record(self,operation:str,elapsed_ms:float)->None:
        bucket=self.samples.setdefault(operation,[]);bucket.append(float(elapsed_ms))
        if len(bucket)>self.max_samples:del bucket[:-self.max_samples]
    def measure(self,operation:str):return _Measurement(self,operation)
    def summary(self,operation:str)->dict[str,float]:
        vals=self.samples.get(operation,[])
        return {'count':len(vals),'avg_ms':sum(vals)/len(vals) if vals else 0.0,'p95_ms':percentile(vals,.95),'max_ms':max(vals) if vals else 0.0,'budget_ms':LATENCY_BUDGET_MS.get(operation,float('inf'))}
    def within_budget(self,operation:str)->bool:return self.summary(operation)['p95_ms']<=LATENCY_BUDGET_MS.get(operation,float('inf'))

class _Measurement:
    def __init__(self,profiler:UiLatencyProfiler,operation:str):self.profiler=profiler;self.operation=operation;self.start=0.0
    def __enter__(self):self.start=time.perf_counter();return self
    def __exit__(self,*_):self.profiler.record(self.operation,(time.perf_counter()-self.start)*1000.0)
