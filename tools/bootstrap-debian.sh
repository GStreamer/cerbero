#!/bin/sh

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

if test $DISTRO = "ubuntu"; then
    mirror=http://archive.ubuntu.com/ubuntu
    cerbero_distro=debian
elif test $DISTRO = "debian"; then
    mirror=http://ftp.debian.org/debian
    cerbero_distro=debian
else
    die "invalid distro $DISTRO"
fi

cerbero_distro_version="$DISTRO"_"$DISTRO_VERSION"

echo "bootstraping $DISTRO-$DISTRO_VERSION"
debootstrap --arch=$ARCH $DISTRO_VERSION $CHROOT_PATH $mirror

echo "installing sudo"
chroot $CHROOT_PATH apt-get -y --force-yes install sudo

echo "installing git"
chroot $CHROOT_PATH apt-get -y --force-yes install git-core

echo "installing python and python-argparse"
chroot $CHROOT_PATH apt-get -y --force-yes install python python-argparse

echo "installing locales"
chroot $CHROOT_PATH apt-get -y --force-yes install locales
chroot $CHROOT_PATH locale-gen en_GB.UTF-8

echo "installing vim"
chroot $CHROOT_PATH apt-get -y --force-yes install vim
chroot $CHROOT_PATH update-alternatives --set editor /usr/bin/vim.basic
