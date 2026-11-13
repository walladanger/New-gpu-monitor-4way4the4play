"""Frosted dashboard diagnostics controls."""
import tkinter as tk
from ui_resources import StringVar
from tkinter import filedialog

from controls import GlassOverlay
from graph_scene import PANEL,TEXT,MUTED,GRID,font
from diagnostics import session_info,set_log_folder,open_log


class SettingsMenu(GlassOverlay):
    def __init__(self,controller,source):
        self.info=session_info()
        self.status=self.info['warning'] or 'One log per launch; startup, clicks, delays and errors.'
        super().__init__(controller,source,470,310)
        self.path=StringVar(self,str(self.info['next_folder']))
        self.entry=tk.Entry(self,textvariable=self.path,bg=PANEL,fg=TEXT,insertbackground=TEXT,
                            relief='flat',highlightthickness=1,highlightbackground=GRID,font=('Segoe UI',10))
        self.create_window(16,101,anchor='nw',window=self.entry,width=self.width-32,height=30)
        self.entry.bind('<Return>',lambda _:self.save())
        self.bind('<Button-1>',self.click)
        self.render()

    def paint(self,draw):
        draw.text((16,23),'Settings / session diagnostics',fill=TEXT,font=font(16,True),anchor='lm')
        draw.text((self.width-20,23),'x',fill=MUTED,font=font(19),anchor='mm')
        draw.text((16,60),'Save debugging logs to',fill=TEXT,font=font(13),anchor='lm')
        draw.text((16,82),'Full path, for example D:\\DEBUGGING LOGS',fill=MUTED,font=font(11),anchor='lm')
        self.tiles={}
        for index,(label,action) in enumerate((('Browse','browse'),('Save folder','save'),('Open log','log'),('Log folder','folder'))):
            width=(self.width-38)/2
            left=16+(index%2)*(width+6)
            top=145+(index//2)*43
            box=(left,top,left+width,top+34)
            self.tiles[action]=box
            draw.rounded_rectangle(box,radius=6,fill=PANEL,outline=GRID)
            draw.text(((box[0]+box[2])/2,top+17),label,fill=TEXT,font=font(12),anchor='mm')
        words=self.status.split()
        lines=['']
        for word in words:
            if draw.textlength(lines[-1]+' '+word,font=font(11))>self.width-32:
                lines.append(word)
            else:
                lines[-1]+=(' ' if lines[-1] else '')+word
        for i,line in enumerate(lines[:4]):
            draw.text((16,240+i*15),line,fill=MUTED,font=font(11))

    def save(self):
        try:
            set_log_folder(self.path.get())
            self.status='Saved. Current session copied here; next launch writes here from startup.'
        except (OSError,ValueError) as error:
            self.status=str(error)
        self.render()

    def click(self,event):
        if event.y<40 and event.x>self.width-40:
            self.close()
            return
        for action,(left,top,right,bottom) in self.tiles.items():
            if left<=event.x<=right and top<=event.y<=bottom:
                try:
                    if action=='browse':
                        folder=filedialog.askdirectory(parent=self.root,title='Choose debugging log folder',initialdir=str(self.info['next_folder']))
                        if folder:
                            self.path.set(folder)
                    elif action=='save':
                        self.save()
                    else:
                        open_log(folder=action=='folder')
                except OSError as error:
                    self.status=str(error)
                self.render()
                break
