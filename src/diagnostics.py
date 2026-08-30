from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import threading

_LOGGER_NAME='monooled'
_configured_path: Path|None=None


def configure_diagnostics(directory: str|Path) -> logging.Logger:
    global _configured_path
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True); path=(directory/'monooled_runtime.log').resolve()
    logger=logging.getLogger(_LOGGER_NAME); logger.setLevel(logging.INFO); logger.propagate=False
    if _configured_path != path:
        for handler in list(logger.handlers):
            handler.close(); logger.removeHandler(handler)
        handler=RotatingFileHandler(path,maxBytes=2_000_000,backupCount=3,encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s'))
        logger.addHandler(handler); _configured_path=path
    def excepthook(exc_type,exc,tb):
        logger.critical('Unhandled exception',exc_info=(exc_type,exc,tb))
        sys.__excepthook__(exc_type,exc,tb)
    sys.excepthook=excepthook
    if hasattr(threading,'excepthook'):
        def thread_hook(args): logger.critical('Unhandled thread exception',exc_info=(args.exc_type,args.exc_value,args.exc_traceback))
        threading.excepthook=thread_hook
    return logger


def get_logger(name: str='app') -> logging.Logger:
    return logging.getLogger(f'{_LOGGER_NAME}.{name}')
