#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim:fenc=utf-8

from glob import glob
from pathlib import Path
from datetime import date
import asyncio
import asyncssh
import logging
import re
import os
import sys

dry_run = os.environ.get("UPLOAD_DRY_RUN", "false").lower().strip() in ("1", "yes", "true")
log = logging.getLogger(__name__)

_PKGNAME_REGEX = re.compile(r"""
    \A                              # String start
    wpewebkit-android               # Package name prefix
    -(?P<arch>[\w^\d]\w*)           # Architecture
    -(?P<version>\d[\d.]*\d)        # Version
    (?:-(?P<kind>runtime))?         # Is it a runtime package?
    (?:-(?P<date>\d{8})             # Optional date..
        (?P<revision>[A-Z]))?       #   ..and revision
    \.tar\.xz                       # Suffixes
    \Z                              # String end
    """, re.VERBOSE)


class PackageSpec:
    arch: str
    version: str
    kind: str or None
    date: str or None
    revision: str or None

    def __init__(self, pkgname):
        m = _PKGNAME_REGEX.match(pkgname)
        if m is None:
            raise ValueError
        self.__dict__ = m.groupdict()

    @property
    def runtime(self) -> bool:
        return self.kind == "runtime"

    @property
    def datecode(self) -> None or str:
        return None if self.date is None else f"{self.date}{self.revision}"

    def __eq__(self, other) -> bool:
        return self.arch == other.arch \
            and self.version == other.version \
            and self.kind == other.kind \
            and self.date == other.date \
            and self.revision == other.revision

    def __str__(self) -> str:
        return "-".join(item for item in
                        ("wpewebkit-android",
                         self.arch,
                         self.version,
                         self.kind,
                         self.datecode)
                        if item) + ".tar.xz"

    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}("
                f"arch={self.arch!r}, "
                f"version={self.version!r}, "
                f"kind={self.kind!r}, "
                f"date={self.datecode!r}, "
                f"revision={self.revision!r})")


async def with_sftp(fn, *arg, **kw):
    async with asyncssh.connect("wpewebkit.org", port=7575, username="www-data",
                                known_hosts=asyncssh.import_known_hosts(os.getenv("UPLOAD_SSH_KNOWN_HOSTS")),
                                passphrase=os.getenv("UPLOAD_KEY_PASSWD")) as conn:
        async with conn.start_sftp_client() as sftp:
            return await fn(sftp, *arg, **kw)


async def get_existing_package_specs(sftp, path):
    async for item in sftp.scandir(path):
        try:
            yield PackageSpec(item.filename)
        except ValueError:
            pass


async def get_remote_pkgspecs(sftp, remotedir, predicate=None):
    if predicate is None:
        def predicate(_): return True
    return [x async for x in get_existing_package_specs(sftp, remotedir)
            if predicate(x)]


def datestrnow() -> str:
    d = date.today()
    return f"{d.year:04}{d.month:02}{d.day:02}"


def show_progress(srcpath, dstpath, curbytes, totalbytes):
    filename = dstpath.split(b"/")[-1].decode("ascii")
    size = totalbytes / 1024 / 1024
    percent = 100 * curbytes / totalbytes
    print(f"\r{filename} [{size:.2f} MiB] {percent:.1f}% ", flush=True, end="")
    if curbytes >= totalbytes:
        print()


async def upload_tarball(sftp, path: Path, progress: bool):
    try:
        spec = PackageSpec(path.name)
    except ValueError:
        raise SystemExit(f"Invalid tarball name: {path!s}")

    symlink_name = str(spec)

    log.info("parsed %r", spec)
    print("Local tarball:", path)

    remotedir = f"wpewebkit/android/bootstrap/{spec.version}"
    print("Remote location:", remotedir)
    if not await sftp.isdir(remotedir):
        if dry_run:
            log.info("dry-run: Skipped target directory creation")
        else:
            await sftp.mkdir(remotedir)

    if spec.datecode:
        log.warn("Package '%s' already has a datecode, continuing anyway", path)
    else:
        spec.date = datestrnow()
        spec.revision = "A"
        remotespecs = await get_remote_pkgspecs(sftp, remotedir,
                                                lambda x: x.date == spec.date)
        if spec in remotespecs:
            # Find the latest revision, increment by one.
            remotespecs.sort(key=lambda x: x.revision if x.revision else "")
            assert remotespecs[-1].revision
            spec.revision = chr(ord(remotespecs[-1].revision) + 1)

    print("Remote symlink:", symlink_name)
    print("Remote filename:", str(spec))

    if dry_run:
        log.info("dry-run: Skipped package upload and symlink update.")
        return

    progress_handler = None
    if progress:
        progress_handler = show_progress
    await sftp.put(path, f"{remotedir}/{spec!s}",
                   preserve=True, progress_handler=progress_handler)
    try:
        await sftp.remove(f"{remotedir}/{symlink_name}")
    except asyncssh.SFTPError as e:
        print(f"swallowed: {e.code!r} {e!r}")
    await sftp.symlink(f"{spec!s}", f"{remotedir}/{symlink_name}")


async def main(path, progress):
    if dry_run:
        logging.basicConfig(level=logging.INFO)
        log.info("Note: UPLOAD_DRY_RUN was set, SFTP connection still used "
                 "but packages will NOT be uploaded.")
    else:
        logging.basicConfig(level=logging.WARN)
    files = [path]
    if "*" in path:
        files = glob(path)

    for file in files:
        print(f"Uploading {file}")
        await with_sftp(upload_tarball, Path(file), progress)


if __name__ == "__main__":
    try:
        progress = len(sys.argv) > 2 and sys.argv[2] == "--progress"
        asyncio.run(main(sys.argv[1], progress))
    except (OSError, asyncssh.Error) as exc:
        sys.exit("Error: " + str(exc))
