from pathlib import Path
import shutil
import subprocess
import sys

from .environment import build_gstreamer_env


def __run(program: str):
    env = build_gstreamer_env()
    fullpath = shutil.which(program, path=f"{env['GSTREAMER_ROOT']}/bin")
    if not fullpath:
        raise RuntimeError(f"{program} was not found in {env['GSTREAMER_ROOT']}")
    fullpath = str(Path(fullpath).resolve())
    subprocess.check_call([fullpath, *sys.argv], env=env)
