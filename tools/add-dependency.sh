# Adds a new dependency to the build system
# usage:
# sh tools/add-dependency.sh /home/andoni/cerbero/sources/local libtasn1 2.11 http://ftp.gnu.org/gnu/libtasn1/libtasn1-2.11.tar.gz "tar -xvzf"

set -e

PREFIX=$1
DEPENDENCY=$2
VERSION=$3
LOCATION=$4
EXTRACT=$5

SSH_LOGIN="git.keema.collabora.co.uk"
GIT_ROOT="/srv/git.keema.collabora.co.uk/git/gst-sdk"
REMOTE_GIT_ROOT="ssh+git://git.keema.collabora.co.uk/git/gst-sdk"

curdir=`pwd`


set -x
ssh $SSH_LOGIN "git init --shared --bare $GIT_ROOT/$DEPENDENCY.git"
git init $PREFIX/$DEPENDENCY
cd $PREFIX/$DEPENDENCY
wget $LOCATION -O $DEPENDENCY.tarball 

$EXTRACT $DEPENDENCY.tarball

mv $DEPENDENCY-$VERSION/* .
rm $DEPENDENCY.tarball
rm -rf $DEPENDENCY-$VERSION
git add *
git commit -m "Import upstream release $DEPENDENCY-$VERSION"
git remote add origin $REMOTE_GIT_ROOT/$DEPENDENCY.git
git branch upstream
git tag upstream/$VERSION -a -m "Tag upstream release $VERSION"
git branch sdk-$VERSION
git push origin sdk-$VERSION
git push origin upstream
git push --tags

cd $curdir
./cerbero-uninstalled add-recipe $DEPENDENCY $VERSION
