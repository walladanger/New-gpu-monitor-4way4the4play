"""Dispose Tk resources on their owning thread, including cyclic GC from workers.

Pillow's default PhotoImage finalizer calls Tcl directly. A rendering allocation
can trigger cyclic GC of an already closed menu/window on the worker thread.
Queue only the Tcl handle and name, never a widget or callback, for UI disposal.
"""
import queue
import threading
import tkinter as tk
from PIL import ImageTk

_pending=queue.SimpleQueue()


def _delete(kind,interpreter,name,commands):
    try:
        if kind=='image':
            interpreter.call('image','delete',name)
        else:
            if interpreter.getboolean(interpreter.call('info','exists',name)):
                interpreter.globalunsetvar(name)
            for command in commands:
                interpreter.deletecommand(command)
    except tk.TclError:
        pass  # An already destroyed interpreter/resource needs no second disposal.


def _dispose(owner,kind,interpreter,name,commands=()):
    if threading.get_ident()==owner:
        _delete(kind,interpreter,name,commands)
    else:
        _pending.put((owner,kind,interpreter,name,commands))


def drain_resources():
    count=0
    deferred=[]
    while True:
        try:
            owner,kind,interpreter,name,commands=_pending.get_nowait()
        except queue.Empty:
            break
        if owner==threading.get_ident():
            _delete(kind,interpreter,name,commands)
            count+=1
        else:
            deferred.append((owner,kind,interpreter,name,commands))
    for entry in deferred:
        _pending.put(entry)
    return count


class PhotoImage(ImageTk.PhotoImage):
    def __init__(self,*args,**kwargs):
        self._owner=threading.get_ident()
        super().__init__(*args,**kwargs)

    def __del__(self):
        # Pillow 12.x keeps a tkinter.PhotoImage here. Disarm its destructor before
        # releasing it; both image wrappers must avoid Tcl calls from cyclic GC.
        photo=getattr(self,'_PhotoImage__photo',None)
        name=getattr(photo,'name',None)
        if name:
            photo.name=None
            _dispose(self._owner,'image',photo.tk,name)


class _Variable:
    def __init__(self,*args,**kwargs):
        self._owner=threading.get_ident()
        super().__init__(*args,**kwargs)

    def __del__(self):
        interpreter=getattr(self,'_tk',None)
        if interpreter is not None:
            self._tk=None
            commands=tuple(self._tclCommands or ())
            self._tclCommands=None
            _dispose(self._owner,'variable',interpreter,self._name,commands)


class StringVar(_Variable,tk.StringVar):
    pass


class BooleanVar(_Variable,tk.BooleanVar):
    pass
