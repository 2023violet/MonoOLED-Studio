from __future__ import annotations

# UI Craft v1.0 semantic spacing scale. Density changes control geometry and
# default internal rhythm; semantic section/page spacing remains stable and is
# only affected by the user's global UI scale.
_SPACING={
    'space_micro':2,
    'space_tight':4,
    'space_compact':6,
    'space_normal':8,
    'space_group':12,
    'space_section':16,
    'space_section_large':20,
    'space_page':24,
    'space_macro':32,
}

_BASE={
 'compact': {'control':28,'row':28,'pad':8,'font_display':17,'font_body':12,'font_metadata':11,'icon':16,'gap':6,'panel_margin':8,'nav_min':184,'inspector_min':248,'radius_panel':8,'radius_control':6,'radius_pill':10,'radius_menu':5},
 'comfortable': {'control':32,'row':32,'pad':10,'font_display':18,'font_body':13,'font_metadata':12,'icon':16,'gap':8,'panel_margin':10,'nav_min':196,'inspector_min':280,'radius_panel':8,'radius_control':6,'radius_pill':10,'radius_menu':5},
 'spacious': {'control':36,'row':38,'pad':12,'font_display':20,'font_body':14,'font_metadata':13,'icon':18,'gap':10,'panel_margin':12,'nav_min':208,'inspector_min':304,'radius_panel':8,'radius_control':6,'radius_pill':10,'radius_menu':5},
}

def build_ui_metrics(density='comfortable',ui_scale=1.0):
    base=_BASE.get(str(density),_BASE['comfortable'])
    scale=max(.75,min(2.0,float(ui_scale or 1.0)))
    values={**_SPACING,**base}
    return {k:max(1,int(round(v*scale))) for k,v in values.items()}
