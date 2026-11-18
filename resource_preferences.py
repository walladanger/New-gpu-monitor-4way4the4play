"""Bounded, backward-compatible validation of optional system view settings."""
import re

from chart_view import LINE_STYLES,normalize_color

MODES={'cpu':('cpu_percent','cpu_clock'),'ram':('ram_percent','ram_capacity'),
       'disk':('disk_rate','disk_capacity')}
DEFAULTS=('cpu:total','cpu:clock','ram:used_pct','disk:total:read')
WINDOWS={'1 minute','5 minutes','15 minutes','1 hour'}


def sensor(value):
    if not isinstance(value,str) or len(value)>160:
        return None
    return value if re.fullmatch(r'cpu:(total|clock|thread:[0-9]{1,5})|ram:(total|used|available|cached|used_pct)|disk:(total:(read|write)|physical:.+:(read|write)|volume:.+:(total|used|free))',value) else None


def color(value,default):
    try:
        return normalize_color(value) if isinstance(value,str) and len(value)<=9 else default
    except ValueError:
        return default


def panel_state(value,group):
    value=value if isinstance(value,dict) else {}
    mode=value.get('mode') if value.get('mode') in MODES[group] else MODES[group][0]
    selected=value.get('selected')
    selected=list(dict.fromkeys(k for k in selected[:512] if sensor(k))) if isinstance(selected,list) else None
    colors=value.get('colors',{})
    styles=value.get('styles',{})
    return dict(mode=mode,selected=selected,
                style=value.get('style') if value.get('style') in LINE_STYLES else 'Line',
                palette=value.get('palette') if value.get('palette') in ('Original','Spectrum') else 'Original',
                colors={k:color(v,'#56D6BE') for k,v in list(colors.items())[:512] if sensor(k)} if isinstance(colors,dict) else {},
                styles={k:v for k,v in list(styles.items())[:512] if sensor(k) and isinstance(v,str) and v in LINE_STYLES} if isinstance(styles,dict) else {})


def validate_resources(value):
    if not isinstance(value,dict) or not value:
        return {}
    raw=value.get('gauges',[])
    gauges=[]
    for index in range(4):
        spec=raw[index] if isinstance(raw,list) and index<len(raw) and isinstance(raw[index],dict) else {}
        gauges.append(dict(metric=sensor(spec.get('metric')) or DEFAULTS[index],
                           style=spec.get('style') if spec.get('style') in ('Ring','Pie','Arc') else 'Ring',
                           color=color(spec.get('color'),'#56D6BE')))
    raw=value.get('heatmap',{})
    raw=raw if isinstance(raw,dict) else {}
    heatmap=dict(metric=sensor(raw.get('metric')) or 'cpu:total',
                 window=raw.get('window') if isinstance(raw.get('window'),str) and raw['window'] in WINDOWS else '5 minutes',
                 expanded=raw.get('expanded') is True)
    result=dict(gauges=gauges,collapsed=value.get('collapsed') is True,heatmap=heatmap)
    raw=value.get('details',{})
    result['details']={group:raw.get(group) is True for group in MODES} if isinstance(raw,dict) else {}
    for key in ('panels','live_panels'):
        raw=value.get(key,{})
        result[key]={group:panel_state(raw.get(group),group) for group in MODES} if isinstance(raw,dict) else {}
    return result
