"""Shared runtime activity log for monitor.py and app.py - both append to
the same file (config.ACTIVITY_LOG_PATH), so the web panel's Logs page
can show one unified timeline regardless of which process produced a
given line. Short lines under PIPE_BUF make concurrent appends from two
separate processes safe without extra locking.
"""
import logging

import config
import features

_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"


def get_logger(name):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured - avoid duplicate handlers on re-import
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    # features.ENABLE_ACTIVITY_LOG only controls the persisted file (and
    # so the Logs page's Activity log section) - stderr stays on either
    # way, that's just normal terminal visibility, not the "logging
    # feature" a developer would want to turn off.
    if features.ENABLE_ACTIVITY_LOG:
        file_handler = logging.FileHandler(config.ACTIVITY_LOG_PATH)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()  # stderr - still visible in the perch exec/run terminal
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


def tail(n=200):
    """Most-recent-first list of the last n log lines. [] if the log
    doesn't exist yet (neither process has run since setup), OR if
    features.ENABLE_ACTIVITY_LOG is off (no file is ever written)."""
    if not features.ENABLE_ACTIVITY_LOG:
        return []
    try:
        with open(config.ACTIVITY_LOG_PATH) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    return [line.rstrip("\n") for line in lines[-n:]][::-1]
