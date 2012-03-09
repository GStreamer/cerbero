#!/bin/sh

set -e

CHROOT_PREFIX=$1
DISTRO=$2
USER=$3

CHROOT_PATH=$CHROOT_PREFIX/$DISTRO

debootstrap $DISTRO $CHROOT_PATH http://archive.ubuntu.com/ubuntu

cp /etc/resolv.conf $CHROOT_PATH/etc/resolv.conf
cp /etc/hosts $CHROOT_PATH/etc/hosts

echo "$USER:x:1000:1000:$USER,,,:/home/$USER:/bin/bash" >> $CHROOT_PATH/etc/passwd
echo "$USER:x:1000:" >> $CHROOT_PATH/etc/group
echo "$USER ALL=NOPASSWD: ALL" >>$CHROOT_PATH/etc/sudoers

mkdir $CHROOT_PATH/home/$USER
cp ~/.gitconfig $CHROOT_PATH/home/$USER/
mkdir $CHROOT_PATH/home/$USER/.ssh
cp ~/.ssh/id_rsa $CHROOT_PATH/home/$USER/.ssh/
chmod -R 600 CHROOT_PATH/home/$USER/.ssh/
chown $USER:$USER $CHROOT_PATH/home/$USER

mkdir -p $CHROOT_PATH/home/$USER/git/cerbero
cp -r * $CHROOT_PATH/home/$USER/git/cerbero
cp -r .git $CHROOT_PATH/home/$USER/git/cerbero
