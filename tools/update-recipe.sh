# Updates a recipe to a newer version
# usage:
# sh tools/update-recipe.sh /home/andoni/cerbero/sources/local libtasn1 2.11 http://ftp.gnu.org/gnu/libtasn1/libtasn1-2.11.tar.gz "tar -xvzf"

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
cd $PREFIX/$DEPENDENCY
git fetch --all
git checkout upstream
git reset --hard origin/upstream
git rm -r *
wget $LOCATION -O $DEPENDENCY.tarball

$EXTRACT $DEPENDENCY.tarball

mv $DEPENDENCY-$VERSION/* .
rm $DEPENDENCY.tarball
rm -rf $DEPENDENCY-$VERSION
git add *
git commit -m "Import upstream release $DEPENDENCY-$VERSION"
git tag upstream/$VERSION -a -m "Tag upstream release $VERSION"
git branch sdk-$VERSION
git push origin sdk-$VERSION
git push origin upstream
git push --tags
