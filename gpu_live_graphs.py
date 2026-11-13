"""GPU Live Graphs entry point. Run with python or use Start.cmd."""
from diagnostics import configure_logging
configure_logging()
import logging
logging.getLogger('gpu_live_graphs').info('phase=import_gui')
from dashboard import Dashboard, main
logging.getLogger('gpu_live_graphs').info('phase=gui_imported')

if __name__ == "__main__":
    main()
