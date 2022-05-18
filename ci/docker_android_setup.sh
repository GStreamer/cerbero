set -eux

export ANDROID_HOME=$1
export ANDROID_NDK_HOME=$2
DEFAULT_BRANCH=$3

# FIXME: might cause problems if the image is used outside CI
# https://github.blog/2022-04-12-git-security-vulnerability-announced/#cve-2022-24765
git config --global --replace-all safe.directory '*'

mkdir -p /android/sources

curl -o /android/sources/android-ndk.zip https://dl.google.com/android/repository/android-ndk-r21-linux-x86_64.zip
unzip /android/sources/android-ndk.zip -d ${ANDROID_NDK_HOME}/
# remove the intermediate versioned directory
mv ${ANDROID_NDK_HOME}/*/* ${ANDROID_NDK_HOME}/

curl -o /android/sources/android-sdk-tools.zip https://dl.google.com/android/repository/commandlinetools-linux-6200805_latest.zip
unzip /android/sources/android-sdk-tools.zip -d ${ANDROID_HOME}/
mkdir -p ${ANDROID_HOME}/licenses

# Accept licenses. Values taken from:
# $ANDROID_HOME/tools/bin/sdkmanager --sdk_root=$ANDROID_HOME --licenses
# cd $ANDROID_HOME
# for f in licenses/*; do echo "echo \"$(cat $f | tr -d '\n')\" > \${ANDROID_HOME}/$f"; done
echo "601085b94cd77f0b54ff86406957099ebe79c4d6" > ${ANDROID_HOME}/licenses/android-googletv-license
echo "859f317696f67ef3d7f30a50a5560e7834b43903" > ${ANDROID_HOME}/licenses/android-sdk-arm-dbt-license
echo "24333f8a63b6825ea9c5514f83c2829b004d1fee" > ${ANDROID_HOME}/licenses/android-sdk-license
echo "84831b9409646a918e30573bab4c9c91346d8abd" > ${ANDROID_HOME}/licenses/android-sdk-preview-license
echo "33b6a2b64607f11b759f320ef9dff4ae5c47d97a" > ${ANDROID_HOME}/licenses/google-gdk-license
echo "e9acab5b5fbb560a72cfaecce8946896ff6aab9d" > ${ANDROID_HOME}/licenses/mips-android-sysimage-license

# pre-cache deps
export GSTREAMER_ROOT_ANDROID=/android/sources/gstreamer-android
curl -o /android/sources/gstreamer-android.tar.xz https://gstreamer.freedesktop.org/data/pkg/android/1.20.0/gstreamer-1.0-android-universal-1.20.0.tar.xz
mkdir $GSTREAMER_ROOT_ANDROID
tar -xvf /android/sources/gstreamer-android.tar.xz -C $GSTREAMER_ROOT_ANDROID
ls $GSTREAMER_ROOT_ANDROID

git clone -b ${DEFAULT_BRANCH} https://gitlab.freedesktop.org/gstreamer/gstreamer.git /android/sources/gstreamer
export GSTREAMER_ROOT=/android/sources/gstreamer/subprojects

chmod +x $GSTREAMER_ROOT/gst-examples/playback/player/android/gradlew
$GSTREAMER_ROOT/gst-examples/playback/player/android/gradlew --no-daemon --project-dir $GSTREAMER_ROOT/gst-examples/playback/player/android dependencies --refresh-dependencies

chmod +x $GSTREAMER_ROOT/gst-examples/vulkan/android/gradlew
$GSTREAMER_ROOT/gst-examples/vulkan/android/gradlew --no-daemon --project-dir $GSTREAMER_ROOT/gst-examples/vulkan/android dependencies --refresh-dependencies

chmod +x $GSTREAMER_ROOT/gst-docs/examples/tutorials/android/gradlew
$GSTREAMER_ROOT/gst-docs/examples/tutorials/android/gradlew --no-daemon --project-dir $GSTREAMER_ROOT/gst-docs/examples/tutorials/android dependencies --refresh-dependencies

unset GSTREAMER_ROOT_ANDROID

rm -rf /android/sources
