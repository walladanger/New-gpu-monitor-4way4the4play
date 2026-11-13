"""Local exception and native-crash logs, including windowless launches."""
import atexit
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from datetime import datetime
import json
import shutil
import tempfile
import sys
import threading
import time

_configured=False
_native_file=None
_handler=None
_directory=None
_log_path=None
_native_path=None
_next_folder=None
_config_path=None
_warning=None
_last_pulse=0


def _data_directory():
    override=os.environ.get('GPU_LIVE_GRAPHS_DATA_DIR')
    return Path(override) if override else Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local'/'share'))/'GPU Live Graphs'


def _valid_folder(value):
    folder=Path(value).expanduser()
    if not folder.is_absolute():
        raise ValueError('Choose a full path, for example D:\\DEBUGGING LOGS')
    return folder.resolve()


def _probe(folder):
    folder.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryFile(dir=folder):
        pass


def configure_logging():
    global _configured,_native_file,_handler,_directory,_log_path,_native_path,_next_folder,_config_path,_warning
    if _configured:
        return _log_path
    data=_data_directory()
    _config_path=data/'diagnostic-settings.json'
    default=Path('D:/DEBUGGING LOGS') if os.name=='nt' and Path('D:/').exists() and not os.environ.get('GPU_LIVE_GRAPHS_DATA_DIR') else data/'logs'
    requested=default
    try:
        if _config_path.exists():
            if _config_path.stat().st_size>16384:
                raise ValueError('Logging settings file is too large')
            requested=_valid_folder(json.loads(_config_path.read_text(encoding='utf-8')).get('folder',str(default)))
        if os.environ.get('GPU_LIVE_GRAPHS_LOG_DIR'):
            requested=_valid_folder(os.environ['GPU_LIVE_GRAPHS_LOG_DIR'])
        _probe(requested)
    except (OSError,ValueError,TypeError,AttributeError) as error:
        _warning=f'Log folder unavailable; using local fallback: {error}'
        requested=data/'logs'
        try:
            _probe(requested)
        except OSError:
            requested=Path(tempfile.gettempdir())/'GPU-Live-Graphs-logs'
            _probe(requested)
    _directory=_next_folder=requested
    session=datetime.now().strftime('%Y%m%d-%H%M%S-%f')+f'-{os.getpid()}'
    _log_path=requested/f'GPU-Live-Graphs-{session}.log'
    _native_path=requested/f'GPU-Live-Graphs-{session}-native.log'
    logger=logging.getLogger('gpu_live_graphs')
    logger.setLevel(logging.INFO)
    handler=RotatingFileHandler(_log_path,maxBytes=10_000_000,backupCount=2,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(threadName)s] %(message)s'))
    logger.addHandler(handler)
    _handler=handler
    _native_file=_native_path.open('a',encoding='utf-8',buffering=1)
    faulthandler.enable(file=_native_file,all_threads=True)
    atexit.register(_finish)
    def unhandled(exc_type,value,traceback):
        logger.critical('Unhandled exception',exc_info=(exc_type,value,traceback))
    sys.excepthook=unhandled
    threading.excepthook=lambda args:unhandled(args.exc_type,args.exc_value,args.exc_traceback)
    _configured=True
    logger.info('phase=pre_import Starting GPU Live Graphs Python=%s PID=%s log=%s',sys.version.split()[0],os.getpid(),_log_path)
    if _warning:
        logger.warning(_warning)
    pulse()
    return _log_path


def pulse():
    """A blocked GUI/import leaves a stack dump even without a Python exception."""
    global _last_pulse
    now=time.monotonic()
    if _configured and now-_last_pulse>=5:
        faulthandler.dump_traceback_later(30,repeat=True,file=_native_file)
        _last_pulse=now


def session_info():
    configure_logging()
    return {'path':_log_path,'folder':_directory,'next_folder':_next_folder,'warning':_warning}


def _copy_session():
    if _next_folder is None or _next_folder==_directory:
        return
    _handler.flush()
    _native_file.flush()
    for path in [_log_path,_native_path]+list(_directory.glob(_log_path.name+'.*')):
        if path.exists():
            shutil.copy2(path,_next_folder/path.name)


def set_log_folder(value):
    """Validate first, save atomically, copy this session, use for next startup."""
    global _next_folder
    configure_logging()
    folder=_valid_folder(value)
    _probe(folder)
    _config_path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=_config_path.parent,delete=False) as output:
            temporary=Path(output.name)
            json.dump({'folder':str(folder)},output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(_config_path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    _next_folder=folder
    logging.getLogger('gpu_live_graphs').info('Log destination saved: %s; current session copied now and at shutdown',folder)
    _copy_session()
    return folder


def _finish():
    if not _configured:
        return
    logging.getLogger('gpu_live_graphs').info('phase=shutdown Session ending')
    try:
        faulthandler.cancel_dump_traceback_later()
        faulthandler.disable()
        _copy_session()
    except OSError:
        logging.getLogger('gpu_live_graphs').exception('Could not copy final session logs')
    finally:
        _native_file.close()
        _handler.flush()


def open_log(folder=False):
    configure_logging()
    target=_next_folder if folder else _log_path
    if os.name!='nt':
        raise OSError('Open the displayed log path with your file manager')
    os.startfile(str(target))
