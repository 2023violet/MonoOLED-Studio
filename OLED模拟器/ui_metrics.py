from __future__ import annotations

_BASE={
 'compact': {'control':28,'row':28,'pad':8,'font_body':12,'font_small':11,'font_heading':16,'icon':16,'gap':6,'panel_margin':8,'nav_min':168,'inspector_min':248,'radius_panel':8,'radius_control':6,'radius_pill':10,'radius_menu':5},
 'comfortable': {'control':32,'row':32,'pad':10,'font_body':13,'font_small':12,'font_heading':18,'icon':18,'gap':8,'panel_margin':10,'nav_min':180,'inspector_min':280,'radius_panel':8,'radius_control':6,'radius_pill':10,'radius_menu':5},
 'spacious': {'control':36,'row':38,'pad':12,'font_body':14,'font_small':13,'font_heading':20,'icon':20,'gap':10,'panel_margin':12,'nav_min':196,'inspector_min':304,'radius_panel':8,'radius_control':6,'radius_pill':10,'radius_menu':5},
}

def build_ui_metrics(density='comfortable',ui_scale=1.0):
    base=_BASE.get(str(density),_BASE['comfortable'])
    scale=max(.75,min(2.0,float(ui_scale or 1.0)))
    return {k:max(1,int(round(v*scale))) for k,v in base.items()}
