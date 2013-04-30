#! /bin/sh
# Build the Windows cross and native toolchains for x86 and x86_64

WIPE=$1

for a in "w64" "w32"
do
  for p in "lin" "win"
  do
      echo "Building $p-$a toolchain"
      if test "x$WIPE" = "x1"; then
        ./cerbero-uninstalled -c config/mingw-$a-$p.cbc wipe --force
      fi
    ./cerbero-uninstalled -c config/mingw-$a-$p.cbc build toolchain
  done
done
