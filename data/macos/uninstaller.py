#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Amyspark <amy@centricular.com>
# SPDX-License-Identifier: MPL-2.0

import argparse
import os
import subprocess

FILES = """on removeAllFiles(argv)
  set commands to ""
  set kRemoveCommand to "/bin/rm "
  if argv is not equal to {} then
      repeat with thePath in argv
          set kRemoveCommand to (kRemoveCommand & quoted form of thePath & " \n")
      end repeat
      set commands to commands & kRemoveCommand
  end if
  return commands
end removeAllFiles

on run argv
    set commands to removeAllFiles(argv)
    do shell script commands %s
end run
"""

DIRS = """on removeDirectories(argv)
  set commands to ""
  set kRemoveCommand to "/bin/rm -rf "
  if argv is not equal to {} then
      repeat with thePath in argv
          set kRemoveCommand to (kRemoveCommand & quoted form of thePath & " \n")
      end repeat
      set commands to commands & kRemoveCommand
  end if
  return commands
end removeDirectories

on run argv
    set commands to removeDirectories(argv)
    do shell script commands %s
end run
"""

RECEIPTS = """on forget(argv)
  set commands to ""
  set kRemoveCommand to "%s"
  if argv is not equal to {} then
      repeat with thePath in argv
          set commands to commands & (kRemoveCommand & thePath & " \n")
      end repeat
  end if
  return commands
end forget

on run argv
    set commands to forget(argv)
    do shell script commands %s
end run
"""


def volume(user):
    if user:
        return ['--volume', os.environ['HOME']]
    return []


def list_packages(user=False):
    return subprocess.check_output(
        ['pkgutil', *volume(user), '--pkgs=org.freedesktop.gstreamer.*'], encoding='utf-8'
    ).splitlines()


def get_package_info(pkgid, user=False):
    pkg_info = subprocess.check_output(['pkgutil', *volume(user), '--pkg-info', pkgid], encoding='utf-8').splitlines()
    info = {}
    for line in pkg_info:
        k, v = line.split(': ')
        info[k] = v
    return info


def get_files(pkgid, user=False):
    return subprocess.check_output(
        ['pkgutil', *volume(user), '--only-files', '--files', pkgid], encoding='utf-8'
    ).splitlines()


def get_dirs(pkgid, user=False):
    return subprocess.check_output(
        ['pkgutil', *volume(user), '--only-dirs', '--files', pkgid], encoding='utf-8'
    ).splitlines()


def requires_sudo(user):
    if user:
        return ' '
    else:
        return 'with administrator privileges'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Uninstall GStreamer packages')
    parser.add_argument('--user', action='store_true', help='Uninstall user-level packages')

    args = parser.parse_args()

    gstreamer = list_packages(args.user)
    information = {p: get_package_info(p, args.user) for p in gstreamer}
    print('This script will uninstall the following packages:')
    for p in gstreamer:
        i = information[p]
        print(f"\t{p} == {i['version']}")
    confirmation = input('Do you confirm uninstallation? [y/N]: ')
    if confirmation.capitalize() != 'Y':
        exit(1)

    directories = set()
    files = set()
    for p in gstreamer:
        i = information[p]
        location = os.path.join(i['volume'], i['location'])
        for f in get_dirs(p, args.user):
            directories.add(os.path.join(location, f))
        for f in get_files(p, args.user):
            files.add(os.path.join(location, f))

    if not args.user:
        print('You may be asked for administrative permissions now.')
    print('Cleaning files...')
    scpt = FILES % (requires_sudo(args.user))
    subprocess.run(['osascript', '-', *files], input=scpt.encode(), check=True)
    print('Cleaning directories...')
    scpt = DIRS % (requires_sudo(args.user))
    subprocess.run(['osascript', '-', *directories], input=scpt.encode(), check=True)
    print('Cleaning receipts...')
    scpt = RECEIPTS % ('pkgutil ' + ' '.join(volume(args.user)) + ' --forget ', requires_sudo(args.user))
    subprocess.run(['osascript', '-', *gstreamer], input=scpt.encode(), check=True)
