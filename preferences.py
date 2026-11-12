"""Versioned, validated preferences with atomic replacement and safe fallback."""
from datetime import datetime
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import uuid

from chart_view import LINE_STYLES, normalize_color

HISTORY_NAMES={'1 minute','5 minutes','15 minutes','1 hour'}
METRIC_KEYS={'utilization','memory','temperature','power'}


def identity(value):
    return value if isinstance(value,str) and 0<len(value)<=160 else None


def view(value):
    if not isinstance(value,dict):
        return {}
    history=value.get('history')
    result={'gpu':identity(value.get('gpu')),'history':history if isinstance(history,str) and history in HISTORY_NAMES else '1 minute'}
    colors,styles={},{}
    raw=value.get('colors',{})
    if isinstance(raw,dict):
        for uid,color in list(raw.items())[:256]:
            if identity(uid) and isinstance(color,str) and len(color)<10:
                try:
                    colors[uid]=normalize_color(color)
                except ValueError:
                    pass
    raw=value.get('styles',{})
    if isinstance(raw,dict):
        styles={uid:style for uid,style in list(raw.items())[:256] if identity(uid) and isinstance(style,str) and style in LINE_STYLES}
    result.update(colors=colors,styles=styles,focus=identity(value.get('focus')))
    for key,maximum,default in (('zoom',1800,1),('lag',3600,0)):
        number=value.get(key,default)
        result[key]=float(number) if isinstance(number,(int,float)) and not isinstance(number,bool) and math.isfinite(number) and 0<=number<=maximum else default
    if result['zoom']<1:
        result['zoom']=1
    return result


def bounds(value):
    if not isinstance(value,(list,tuple)) or len(value)!=4 or any(type(n) is not int for n in value):
        return None
    x,y,width,height=value
    return [x,y,width,height] if -100000<=x<=100000 and -100000<=y<=100000 and 450<=width<=20000 and 300<=height<=20000 else None


def validate(value):
    if not isinstance(value,dict) or value.get('schema')!=1:
        raise ValueError('Unsupported preferences schema')
    raw=value.get('main',{})
    if not isinstance(raw,dict):
        raw={}
    main=view(raw)
    main.update(bounds=bounds(raw.get('bounds')),maximized=raw.get('maximized') is True,topmost=raw.get('topmost') is True)
    charts=raw.get('charts',{})
    main['charts']={key:view(data) for key,data in charts.items() if key in METRIC_KEYS} if isinstance(charts,dict) else {}
    detached=[]
    raw=value.get('detached',[])
    if isinstance(raw,list):
        for data in raw[:12]:
            if not isinstance(data,dict) or not isinstance(data.get('metric'),str) or data.get('metric') not in METRIC_KEYS:
                continue
            item=view(data)
            item.update(metric=data['metric'],bounds=bounds(data.get('bounds')),maximized=data.get('maximized') is True)
            detached.append(item)
    return {'schema':1,'main':main,'detached':detached}


class Preferences:
    def __init__(self,path):
        self.path=Path(path)
        self.error=None
        self.preserve_invalid=False
        self.read_only=False
        self.last_written=None

    def load(self):
        if not self.path.exists():
            return {}
        try:
            if self.path.stat().st_size>256000:
                raise ValueError('Preferences file is too large')
            raw=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(raw,dict) and isinstance(raw.get('schema'),int) and raw['schema']>1:
                self.read_only=True
                raise ValueError('Preferences belong to a newer app; original file will be retained')
            result=validate(raw)
            self.last_written=json.dumps(result,sort_keys=True)
            return result
        except (OSError,ValueError,TypeError,RecursionError,OverflowError) as error:
            self.error=str(error)
            self.preserve_invalid=not self.read_only
            return {}

    def save(self,state):
        if self.read_only:
            return False
        state=validate(state)
        canonical=json.dumps(state,sort_keys=True)
        if canonical==self.last_written:
            return False
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.path.parent,prefix='preferences-',suffix='.tmp',delete=False) as output:
                temporary=Path(output.name)
                json.dump(state,output,indent=2,allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            if self.preserve_invalid and self.path.exists():
                backup=self.path.with_name('preferences-invalid-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json')
                shutil.copy2(self.path,backup)
            # os.replace is atomic for same-filesystem publication.
            # https://docs.python.org/3.11/library/os.html#os.replace
            temporary.replace(self.path)
            self.preserve_invalid=False
            self.last_written=canonical
            self.error=None
            return True
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
