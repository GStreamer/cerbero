#!/bin/sh
# usage:
# $ sudo sh tools/build-release.sh ~/cerbero/roots redhat fedora 16 x86_64 username sdk-release-sdk-2012.11
# $ sudo sh tools/build-release.sh ~/cerbero/roots debian debian squeeze i386 username sdk-release-sdk-2012.11
set -e

CHROOT_PREFIX=$1
DISTRO_FAMILY=$2
DISTRO=$3
DISTRO_VERSION=$4
ARCH=$5
USER=$6
TAG=$7

CHROOT_PATH=$CHROOT_PREFIX/$DISTRO-$DISTRO_VERSION-$ARCH
BASEDIR=$(dirname $0)

die() {
    echo "ERROR: $@"
    exit 1
}

sh $BASEDIR/bootstrap-$DISTRO_FAMILY.sh $CHROOT_PREFIX $DISTRO $DISTRO_VERSION $ARCH $USER

if test $DISTRO_FAMILY = "redhat"; then
    CHROOT_PATH=$CHROOT_PATH/root
fi

cerbero_distro=Distro.`echo $DISTRO_FAMILY | awk '{print toupper($0)}'`
cerbero_distro_version=DistroVersion.`echo "$DISTRO"_"$DISTRO_VERSION" | awk '{print toupper($0)}'`

if test $ARCH = "i386" || test $ARCH = "x86"; then
    cerbero_arch=X86
elif test $ARCH = "amd64" || test $ARCH = "x86_64"; then
    ARCH=x86_64
    cerbero_arch=X86_64
else
    die "Architecture $ARCH not supported"
fi

cerbero_arch=Architecture.$cerbero_arch
cerbero_target_arch=$cerbero_arch
cerbero_host=$ARCH-pc-linux-gnu
cerbero_build=$ARCH-pc-linux-gnu

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

echo "generating cerbero tarball"
make dist-tarball
echo "extracting tarball at $CHROOT_PATH/home/$USER/git"
mkdir -p $CHROOT_PATH/home/$USER/git
tar --bzip2 -xvf dist/cerbero-0.1.0.tar.bz2 -C $CHROOT_PATH/home/$USER/git/
cp -rf .git $CHROOT_PATH/home/$USER/git/cerbero-0.1.0/

echo "generating $CHROOT_PATH/home/$USER/.cerbero/cerbero.cdc from template"
mkdir -p $CHROOT_PATH/home/$USER/.cerbero
cp -f tools/cerbero.cbc.template $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
echo "distro = $cerbero_distro" >> $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
echo "distro_version = $cerbero_distro_version" >> $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
echo "arch = $cerbero_arch" >> $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
echo "target_arch = $cerbero_target_arch" >> $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
echo "host = \"$cerbero_host\"" >> $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
echo "build = \"$cerbero_build\"" >> $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
if test $TAG != ""; then
    echo "force_git_commit = \"$TAG\"" >> $CHROOT_PATH/home/$USER/.cerbero/cerbero.cbc
fi

sudo mkdir -p $CHROOT_PATH/opt/gstreamer-sdk

echo "fixing permissions"
chown -R $USER:$USER $CHROOT_PATH/home/$USER
chown -R $USER:$USER $CHROOT_PATH/opt/gstreamer-sdk

echo "mounting /proc and /sys"
mount -o bind /proc $CHROOT_PATH/proc
mount -o bind /sys $CHROOT_PATH/sys

echo "reset root password"
chroot $CHROOT_PATH sed -i  's/root:\*/root:/g' /etc/shadow

echo "chroot created"

echo "starting the build"
echo "cd ~/git/cerbero-0.1.0
./cerbero-uninstalled bootstrap
./cerbero-uninstalled wipe --force
./cerbero-uninstalled package gstreamer-sdk" > $CHROOT_PATH/home/$USER/run_package

chroot $CHROOT_PATH  su $USER /home/$USER/run_package
