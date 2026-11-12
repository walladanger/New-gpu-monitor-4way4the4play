"""Local exception and native-crash logs, including windowless launches."""
import atexit
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading

_configured=False
_native_file=None


def configure_logging():
    global _configured,_native_file
    if _configured:
        return
    directory=Path(__file__).resolve().parent/'logs'
    directory.mkdir(exist_ok=True)
    logger=logging.getLogger('gpu_live_graphs')
    logger.setLevel(logging.INFO)
    handler=RotatingFileHandler(directory/'app.log',maxBytes=1_000_000,backupCount=2,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    _native_file=(directory/f'native-crash-{os.getpid()}.log').open('a',encoding='utf-8',buffering=1)
    faulthandler.enable(file=_native_file,all_threads=True)
    atexit.register(_native_file.close)
    atexit.register(faulthandler.disable)
    def unhandled(exc_type,value,traceback):
        logger.critical('Unhandled exception',exc_info=(exc_type,value,traceback))
    sys.excepthook=unhandled
    threading.excepthook=lambda args:unhandled(args.exc_type,args.exc_value,args.exc_traceback)
    logger.info('Starting GPU Live Graphs, Python %s, PID %s',sys.version.split()[0],os.getpid())
    _configured=True
