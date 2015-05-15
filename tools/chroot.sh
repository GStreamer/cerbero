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

cp /etc/resolv.conf $CHROOT_PATH/etc/resolv.conf
cp /etc/hosts $CHROOT_PATH/etc/hosts
hostname=$USER-$DISTRO-$DISTRO_VERSION-$ARCH-chroot
# hostnames cannot contain _
hostname=$(echo $hostname | sed s/'_'/'-'/g)
#echo $hostname > $CHROOT_PATH/etc/hostname
#chroot $CHROOT_PATH hostname $hostname
echo $hostname > $CHROOT_PATH/etc/debian_chroot

userid=$(grep $USER /etc/passwd | cut -d: -f3)
echo "$USER:x:$userid:$userid:$USER,,,:/home/$USER:/bin/bash" >> $CHROOT_PATH/etc/passwd
echo "$USER::15460::::::" >> $CHROOT_PATH/etc/shadow
echo "$USER:x:$userid:" >> $CHROOT_PATH/etc/group
echo "$USER ALL=NOPASSWD: ALL" >> $CHROOT_PATH/etc/sudoers

echo "installing sudo"
chroot $CHROOT_PATH apt-get -y --force-yes install sudo

echo "copying user git/ssh/gpg configurations"
mkdir -p $CHROOT_PATH/home/$USER

cp -f /home/$USER/.gitconfig $CHROOT_PATH/home/$USER/
cp -rf /home/$USER/.ssh $CHROOT_PATH/home/$USER/
chmod -R 700 $CHROOT_PATH/home/$USER/.ssh/
cp -rf /home/$USER/.gnupg $CHROOT_PATH/home/$USER/
chmod -R 700 $CHROOT_PATH/home/$USER/.gnupg/

echo "copying vim configuration files and installing/setting vim as default editor"
cp -f /home/$USER/.vimrc $CHROOT_PATH/home/$USER/
cp -rf /home/$USER/.vim $CHROOT_PATH/home/$USER/
chroot $CHROOT_PATH apt-get -y --force-yes install vim
chroot $CHROOT_PATH update-alternatives --set editor /usr/bin/vim.basic

echo "installing git"
chroot $CHROOT_PATH apt-get -y --force-yes install git-core

echo "installing python and python-argparse"
chroot $CHROOT_PATH apt-get -y --force-yes install python python-argparse

echo "installing locales"
chroot $CHROOT_PATH apt-get -y --force-yes install locales
chroot $CHROOT_PATH locale-gen en_GB.UTF-8

echo "generating cerbero tarball"
make dist-tarball
echo "extracting tarball at $CHROOT_PATH/home/$USER/git"
mkdir -p $CHROOT_PATH/home/$USER/git
tar --bzip2 -xvf dist/cerbero-0.1.0.tar.bz2 -C $CHROOT_PATH/home/$USER/git/
cp -rf .git $CHROOT_PATH/home/$USER/git/cerbero-0.1.0/

echo "generating $CHROOT_PATH/home/$USER/.cerbero/cerbero.cdc from template"
mkdir -p $CHROOT_PATH/home/$USER/.cerbero
cp -f tools/cerbero.cbc.template $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
echo "distro = \"$cerbero_distro\"" >> $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
echo "distro_version = \"$cerbero_distro_version\"" >> $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
sudo mkdir -p $CHROOT_PATH/opt/gstreamer-1.0

echo "fixing permissions"
chown -R $USER:$USER $CHROOT_PATH/home/$USER
chown -R $USER:$USER $CHROOT_PATH/opt/gstreamer-1.0

echo "mounting /proc and /sys"
mount -o bind /proc $CHROOT_PATH/proc
mount -o bind /sys $CHROOT_PATH/sys

echo "chroot created"
