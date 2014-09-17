#! /bin/sh
# Build the Windows cross and native toolchains for x86 and x86_64

WIPE=$1
CURDIR=`pwd`
set -e

for a in "w64" "w32"
do
  for p in "lin" "win"
  do
      echo "Building $p-$a toolchain"
      if test "x$WIPE" = "x1"; then
        ./cerbero-uninstalled -c config/mingw-$a-$p.cbc wipe --force
      fi
    ./cerbero-uninstalled -c config/mingw-$a-$p.cbc build toolchain


    if test "x$a" = "xw64"; then
        ARCH=x86_64
    else
        ARCH=x86
    fi
    if test "x$p" = "xwin"; then
        PLAT=windows
    else
        PLAT=linux
    fi
    TC=mingw-$a-gcc-4.7.3-$PLAT-$ARCH.tar.xz
    echo "Creating tarball $TC"
    cd  ~/mingw/$PLAT/$a
    XZ_OPT=-9 tar cJf $CURDIR/$TC *
    cd $CURDIR
    md5sum  $TC | awk '{print $1}' > $TC.md5
    sha1sum $TC | awk '{print $1}' > $TC.sha1
  done
done
