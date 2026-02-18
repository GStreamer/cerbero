from pathlib import Path
import shutil
import subprocess
import sys

from gstreamer_libs import gstreamer_env


def __run(program: str):
    env, runtime_path = gstreamer_env()
    fullpath = shutil.which(program, path=runtime_path)
    if not fullpath:
        raise RuntimeError(f'{program} was not found in {runtime_path}')
    fullpath = str(Path(fullpath).resolve())
    try:
        subprocess.check_call([fullpath, *sys.argv[1:]], env=env)
    except KeyboardInterrupt:
        return 130
    except subprocess.CalledProcessError as e:
        return e.returncode
    return 0
