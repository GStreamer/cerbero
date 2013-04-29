#! /bin/sh
# Build the Windows cross and native toolchains for x86 and x86_64

for a in "w64" "w32"
do
  for p in "lin" "win"
  do
    ./cerbero-uninstalled -c config/mingw-$a-$p.cbc wipe --force
    ./cerbero-uninstalled -c config/mingw-$a-$p.cbc build toolchain
  done
done
