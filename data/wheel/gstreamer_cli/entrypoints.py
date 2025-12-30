from pathlib import Path
import shutil
import subprocess
import sys

from gstreamer_runtime import gstreamer_env


def __run(program: str):
    env, runtime_path = gstreamer_env()
    fullpath = shutil.which(program, path=runtime_path)
    if not fullpath:
        raise RuntimeError(f'{program} was not found in {runtime_path}')
    fullpath = str(Path(fullpath).resolve())
    subprocess.check_call([fullpath, *sys.argv[1:]], env=env)
