# Adds a new dependency to the build system
# usage:
# sh tools/add-dependency.sh /home/andoni/cerbero/sources/local libtasn1 2.11 http://ftp.gnu.org/gnu/libtasn1/libtasn1-2.11.tar.gz "tar -xvzf"

PREFIX=$1
DEPENDENCY=$2
VERSION=$3
LOCATION=$4
EXTRACT=$5

SSH_LOGIN="amorales@git.keema.collabora.co.uk"
GIT_ROOT="/srv/git.keema.collabora.co.uk/git/gst-sdk"
REMOTE_GIT_ROOT="ssh+git://amorales@git.keema.collabora.co.uk/git/gst-sdk"

curdir=`pwd`

ssh $SSH_LOGIN "git init --bare $GIT_ROOT/$DEPENDENCY.git"
git init $PREFIX/$DEPENDENCY
chdir $PREFIX/$DEPENDENCY
wget $LOCATION

$EXTRACT $DEPENDENCY*

mv $DEPENDENCY-$VERSION/* .
rm *.tar.xz
rm *.tar.gz
rm *.tar.bz
rm *.zip
git add *
git commit -m "Import upstream release $DEPENDENCY-$VERSION"
git remote add origin $REMOTE_GIT_ROOT/$DEPENDENCY.git
git branch upstream
git tag upstream/$VERSION -a -m "Tag upstream release $VERSION"
git branch sdk-$VERSION
git push origin sdk-$VERSION
git push origin upstream
git push --tags

chdir $curdir
echo "from cerbero import recipe\n\
\n\
class Recipe(recipe.Recipe):\n\
    name = '$DEPENDENCY'\n\
    version = '$VERSION'\
" > cerbero/recipes/$DEPENDENCY.recipe

