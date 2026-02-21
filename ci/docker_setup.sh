#! /bin/bash

set -e

git config --global user.email "cerbero@gstreamer.freedesktop.org"
git config --global user.name  "Cerbero Build System"

mkdir $HOME/.cerbero
echo "allow_parallel_build=True" > $HOME/.cerbero/cerbero.cbc
echo "use_ccache=True" >> $HOME/.cerbero/cerbero.cbc
echo "local_sources=\"/cerbero-sources\"" >> localconf.cbc
echo "home_dir=\"/cerbero-build\"" >> localconf.cbc
./cerbero-uninstalled -t -c localconf.cbc fetch-bootstrap --jobs=16
./cerbero-uninstalled -t -c localconf.cbc fetch-package --jobs=16 gstreamer-1.0
./cerbero-uninstalled -t -c localconf.cbc bootstrap -y --build-tools=no --toolchains=no
./cerbero-uninstalled -t -v rust -c localconf.cbc -c config/cross-win32.cbc fetch-bootstrap --jobs=16
./cerbero-uninstalled -t -v rust -c localconf.cbc -c config/cross-win32.cbc fetch-package --jobs=16 gstreamer-1.0
./cerbero-uninstalled -t -v rust -c localconf.cbc -c config/cross-win64.cbc fetch-bootstrap --jobs=16
./cerbero-uninstalled -t -v rust -c localconf.cbc -c config/cross-win64.cbc fetch-package --jobs=16 gstreamer-1.0
./cerbero-uninstalled -t -v rust -c localconf.cbc -c config/cross-android-universal.cbc fetch-bootstrap --jobs=16
./cerbero-uninstalled -t -v rust -c localconf.cbc -c config/cross-android-universal.cbc fetch-package --jobs=16 gstreamer-1.0
rm -rf /cerbero-build/{dist,logs,sources}
rm -f /cerbero-build/{linux,windows,android}*.cache
