#!/bin/sh

set -e
set -x

CHROOT_PREFIX=$1
DISTRO=$2
DISTRO_VERSION=$3
ARCH=$4
USER=$5

CHROOT_PATH=$CHROOT_PREFIX/$DISTRO-$DISTRO_VERSION-$ARCH

die() {
    echo "ERROR: $@"
    exit 1
}

echo "bootstraping $DISTRO-$DISTRO_VERSION"

apt-get install yum rpm

echo "installing mock"

set +e
groupadd -r mock
usermod -G $USER mock
git clone git://git.fedorahosted.org/git/mock.git mock
set -e

cd mock
./autogen.sh
./configure
make
make install
echo "config_opts['basedir'] = '$CHROOT_PREFIX'" > /usr/local/etc/mock/site-defaults.cfg
mock -r $DISTRO-$DISTRO_VERSION-$ARCH --init --resultdir=~/mock

echo "installing yum git and vim"
mock -r $DISTRO-$DISTRO_VERSION-$ARCH install git yum vim --resultdir=~/mock
