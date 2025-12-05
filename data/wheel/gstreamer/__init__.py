import os
import sys
from .environment import build_gstreamer_env


def setup_python_environment():
    env = build_gstreamer_env()

    os.environ.update(env)

    sys.path.append(env['GST_PYTHONPATH_1_0'])
