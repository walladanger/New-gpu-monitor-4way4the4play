"""Scrollable resource options using the dashboard's translucent, blurred surface."""
import colorsys
import tkinter as tk

from controls import GlassOverlay
from graph_scene import PANEL,TEXT,MUTED,GRID,font
from chart_view import normalize_color
from ui_resources import StringVar


def option(label,action=None,checked=None,submenu=None):
    return dict(label=label,action=action,checked=checked,submenu=submenu)


class ResourceMenu(GlassOverlay):
    def __init__(self,source,title,rows):
        self.title,self.rows=title,rows
        self.offset=0
        self.stack=[]
        super().__init__(source.winfo_toplevel(),source,370,450)
        self.bind('<Button-1>',self.click)
        self.bind('<MouseWheel>',self.wheel)
        self.bind('<Button-4>',lambda _:self.scroll(-1))
        self.bind('<Button-5>',lambda _:self.scroll(1))
        self.bind('<Up>',lambda _:self.scroll(-1))
        self.bind('<Down>',lambda _:self.scroll(1))
        self.focus_set()
        self.render()

    @property
    def page_size(self):
        return max(1,int((self.height-78)//30))

    def paint(self,draw):
        self.items=self.rows()
        self.offset=max(0,min(self.offset,max(0,len(self.items)-self.page_size)))
        draw.text((16,22),('‹  ' if self.stack else '')+self.title,fill=TEXT,font=font(14,True),anchor='lm')
        draw.text((self.width-20,22),'×',fill=MUTED,font=font(17),anchor='mm')
        for index,row in enumerate(self.items[self.offset:self.offset+self.page_size]):
            y=52+index*30
            label=row['label']
            while len(label)>1 and draw.textlength(label,font=font(12))>self.width-70:
                label=label[:-2]+'…'
            checked=row['checked']
            if checked is not None:
                draw.ellipse((15,y+9,25,y+19),outline='#56d6be' if checked else MUTED,
                             fill='#56d6be' if checked else None)
            draw.text((35,y+14),label,fill=TEXT if checked is not False else MUTED,font=font(12),anchor='lm')
            if row['submenu']:
                draw.text((self.width-20,y+14),'›',fill=MUTED,font=font(16),anchor='mm')
        if len(self.items)>self.page_size:
            draw.text((16,self.height-18),f'{self.offset+1}–{min(len(self.items),self.offset+self.page_size)} / {len(self.items)} · scroll for more',fill=MUTED,font=font(11),anchor='lm')

    def choose(self,index):
        row=self.items[index]
        if row['submenu']:
            self.stack.append((self.title,self.rows,self.offset))
            self.title,self.rows=row['label'],row['submenu']
            self.offset=0
        elif row['action']:
            row['action']()
        if not self.closed:
            self.render()

    def click(self,event):
        if event.y<40:
            if event.x>self.width-40:
                self.close()
            elif self.stack:
                self.title,self.rows,self.offset=self.stack.pop()
                self.render()
            return
        index=self.offset+int((event.y-52)//30)
        if event.y>=52 and self.offset<=index<min(len(self.items),self.offset+self.page_size):
            self.choose(index)

    def scroll(self,direction):
        self.offset=max(0,min(max(0,len(self.items)-self.page_size),self.offset+direction))
        self.render()
        return 'break'

    def wheel(self,event):
        return self.scroll(-1 if event.delta>0 else 1)


class ColorMenu(GlassOverlay):
    def __init__(self,source,color,apply):
        self.apply=apply
        self.status='Type #RRGGBB or drag the hue slider'
        self.color=normalize_color(color)
        self.sliding=False
        super().__init__(source.winfo_toplevel(),source,340,170)
        self.value=StringVar(self,self.color)
        self.entry=tk.Entry(self,textvariable=self.value,bg=PANEL,fg=TEXT,insertbackground=TEXT,
                            relief='flat',highlightthickness=1,highlightbackground=GRID)
        self.create_window(18,55,anchor='nw',window=self.entry,width=self.width-36,height=28)
        self.trace=self.value.trace_add('write',self.edit)
        self.bind('<Button-1>',self.click)
        self.bind('<B1-Motion>',lambda event:self.hue(event.x) if self.sliding else None)
        self.bind('<ButtonRelease-1>',self.release)
        self.render()

    def paint(self,draw):
        draw.text((18,24),'Trace color',fill=TEXT,font=font(15,True),anchor='lm')
        draw.text((self.width-20,24),'×',fill=MUTED,font=font(17),anchor='mm')
        for x in range(18,self.width-18):
            rgb=tuple(round(v*255) for v in colorsys.hsv_to_rgb((x-18)/(self.width-36),.72,.95))
            draw.line((x,100,x,114),fill=rgb)
        rgb=tuple(int(self.color[i:i+2],16)/255 for i in (1,3,5))
        x=18+colorsys.rgb_to_hsv(*rgb)[0]*(self.width-36)
        draw.rectangle((x-2,96,x+2,118),fill=TEXT,outline=PANEL)
        draw.text((18,145),self.status,fill=MUTED,font=font(11),anchor='lm')

    def edit(self,*_):
        try:
            color=normalize_color(self.value.get())
        except ValueError:
            self.status='Enter a complete #RRGGBB or #RGB color'
        else:
            self.color=color
            self.apply(color)
            self.status='Color applied'
        self.render()

    def hue(self,x):
        rgb=tuple(round(v*255) for v in colorsys.hsv_to_rgb(max(0,min(1,(x-18)/(self.width-36))),.72,.95))
        self.value.set('#'+''.join(f'{v:02X}' for v in rgb))

    def click(self,event):
        if event.y<40 and event.x>self.width-40:
            self.close()
        elif 94<=event.y<=120:
            self.sliding=True
            self.grab_set()
            self.hue(event.x)

    def release(self,event):
        if self.sliding:
            self.hue(event.x)
            self.sliding=False
            self.grab_release()

    def close(self):
        if not self.closed and hasattr(self,'trace'):
            self.value.trace_remove('write',self.trace)
        super().close()
