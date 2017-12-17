#!/bin/sh

# Requires rpm >= 4.10.0 see http://bugs.debian.org/cgi-bin/bugreport.cgi?bug=683759
# $ sudo dpkg --force-all -i rpm-common_4.10.0-5_amd64.deb  librpm3_4.10.0-5_amd64.deb \
# librpmio3_4.10.0-5_amd64.deb  librpmsign1_4.10.0-5_amd64.deb librpmbuild3_4.10.0-5_amd64.deb \
# rpm_4.10.0-5_amd64.deb rpm2cpio_4.10.0-5_amd64.deb  liblzma5_5.1.1alpha+20120614-1_amd64.deb \
# python-rpm_4.10.0-5_amd64.deb

set -e

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
git clone "https://github.com/rpm-software-management/mock" mock
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
