from pathlib import Path
import shutil
import subprocess
import sys
import os

from gstreamer_libs import gstreamer_env


def __run(program: str):
    env, runtime_path = gstreamer_env()
    fullpath = shutil.which(program, path=runtime_path)
    if not fullpath:
        raise RuntimeError(f'{program} was not found in {runtime_path}')
    fullpath = str(Path(fullpath).resolve())
    # Restore terminal state on exit if the called program changed the state,
    # such as gst-play
    if os.name == 'posix':
        import termios

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
    try:
        subprocess.check_call([fullpath, *sys.argv[1:]], env=env)
    except KeyboardInterrupt:
        return 130
    except subprocess.CalledProcessError as e:
        return e.returncode
    finally:
        if os.name == 'posix':
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return 0
