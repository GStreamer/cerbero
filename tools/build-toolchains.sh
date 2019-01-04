#! /bin/sh
# Build the Windows cross and native toolchains for x86 and x86_64

WIPE=$1
CURDIR=`pwd`
set -e

for p in "lin" "win"
do
    echo "Building $p-multilib toolchain"
    if test "x$WIPE" = "x1"; then
      ./cerbero-uninstalled -c config/mingw-multilib-$p.cbc wipe --force
    fi
  ./cerbero-uninstalled -c config/mingw-multilib-$p.cbc bootstrap --build-tools-only
  ./cerbero-uninstalled -c config/mingw-multilib-$p.cbc build toolchain

  ARCH=x86_64
  if test "x$p" = "xwin"; then
      PLAT=windows
  else
      PLAT=linux
  fi
  TC=mingw-6.0.0-gcc-8.2.0-$PLAT-multilib.tar.xz
  echo "Creating tarball $TC"
  cd  ~/mingw/$PLAT/multilib
  XZ_OPT=-9 tar cJf $CURDIR/$TC *
  cd $CURDIR
  md5sum  $TC | awk '{print $1}' > $TC.md5
  sha1sum $TC | awk '{print $1}' > $TC.sha1
  sha256sum $TC | awk '{print $1}' > $TC.sha256
done
