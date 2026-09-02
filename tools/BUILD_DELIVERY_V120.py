#!/usr/bin/env python3
"""Compatibility entry point for the former V12-named source packager."""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from BUILD_SOURCE_DELIVERY import *  # noqa: F401,F403
from BUILD_SOURCE_DELIVERY import main


if __name__ == '__main__':
    raise SystemExit(main())
