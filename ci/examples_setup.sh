#!/bin/bash
# vim: set sts=4 sw=4 et :

set -ex

user_branch_exists_in() {
    ./ci/exists_branch_in_user_repo.sh "$1" "$2"
}

clone_gstreamer() {
    local gst_commit="$GST_UPSTREAM_BRANCH"
    local gst_remote="${CI_SERVER_URL}/gstreamer/gstreamer"

    # Two special cases in which we should build examples against
    # a user-specific branch of gstreamer:
    # 1. We have been triggered by gstreamer monorepo CI
    #    - ci/gitlab/trigger_cerbero_pipeline.py
    # 2. We are running as part of CI for a cerbero merge request
    if [[ -n ${CI_GSTREAMER_PATH} ]]; then
        gst_commit="${CI_GSTREAMER_REF_NAME}"
        gst_remote="${CI_SERVER_URL}/${CI_GSTREAMER_PATH}"
        echo "gstreamer trigger CI, using ${gst_commit} in ${gst_remote}"
    elif [[ -n ${CI_GST_PLUGINS_RS_PATH} ]]; then
        echo "gst-plugins-rs trigger CI, using ${gst_commit} in ${gst_remote}"
    elif [[ ${CI_PROJECT_NAMESPACE} != gstreamer ]]; then
        echo "Cerbero merge request, checking for matching branch in user fork of gstreamer"
        if user_branch_exists_in "${CI_PROJECT_NAMESPACE}/gstreamer" "${CI_COMMIT_REF_NAME}"; then
            gst_commit="${CI_COMMIT_REF_NAME}"
            gst_remote="${CI_SERVER_URL}/${CI_PROJECT_NAMESPACE}/gstreamer"
            echo "Found branch ${gst_commit} in ${gst_remote}"
        else
            gst_remote="${CI_SERVER_URL}/gstreamer/gstreamer"
        fi
    fi

    # Clone gstreamer repository to get gst-examples and gst-docs
    rm -rf gstreamer
    git clone "${gst_remote}" -b "${gst_commit}" --depth 1 gstreamer/
}

build_android_examples() {
    clone_gstreamer
    mkdir -p ${OUTPUT_DIR}

    # extract our binaries
    rm -f gstreamer-1.0-android-universal-*-runtime.tar.*
    mkdir ${GSTREAMER_ROOT_ANDROID}
    time tar -C ${GSTREAMER_ROOT_ANDROID} -xf gstreamer-1.0-android-universal-*.tar.*

    # gst-examples - player
    chmod +x ${EXAMPLES_HOME}/gst-examples/playback/player/android/gradlew
    ./ci/run_retry.sh ${EXAMPLES_HOME}/gst-examples/playback/player/android/gradlew --no-daemon --project-dir ${EXAMPLES_HOME}/gst-examples/playback/player/android assembleDebug
    cp ${EXAMPLES_HOME}/gst-examples/playback/player/android/app/build/outputs/apk/debug/*.apk ${OUTPUT_DIR}

    # gst-examples - vulkan
    chmod +x ${EXAMPLES_HOME}/gst-examples/vulkan/android/gradlew
    ./ci/run_retry.sh ${EXAMPLES_HOME}/gst-examples/vulkan/android/gradlew --no-daemon --project-dir ${EXAMPLES_HOME}/gst-examples/vulkan/android assembleDebug
    cp ${EXAMPLES_HOME}/gst-examples/vulkan/android/build/outputs/apk/debug/*.apk ${OUTPUT_DIR}

    # gst-docs android tutorials
    chmod +x ${EXAMPLES_HOME}/gst-docs/examples/tutorials/android/gradlew
    ./ci/run_retry.sh ${EXAMPLES_HOME}/gst-docs/examples/tutorials/android/gradlew --no-daemon --project-dir ${EXAMPLES_HOME}/gst-docs/examples/tutorials/android assembleDebug
    cp ${EXAMPLES_HOME}/gst-docs/examples/tutorials/android/android-tutorial-*/build/outputs/apk/debug/*.apk ${OUTPUT_DIR}
}

build_ios_examples() {
    # install the binaries
    installer -pkg gstreamer-1.0-devel-*-ios-universal.pkg -target CurrentUserHomeDirectory -verbose

    # Clone gstreamer repository to get gst-examples and gst-docs
    clone_gstreamer

    # dump some useful information
    xcodebuild -version
    xcodebuild -showsdks
    echo ${XCODE_BUILD_ARGS} > xcode_buildargs

    # gst-docs ios tutorials
    ./ci/run_retry.sh xcodebuild -showBuildSettings -alltargets -project ${EXAMPLES_HOME}/gst-docs/examples/tutorials/xcode\ iOS/GStreamer\ iOS\ Tutorials.xcodeproj $(cat xcode_buildargs)
    ./ci/run_retry.sh xcodebuild -alltargets -destination generic/platform=iOS -project ${EXAMPLES_HOME}/gst-docs/examples/tutorials/xcode\ iOS/GStreamer\ iOS\ Tutorials.xcodeproj $(cat xcode_buildargs)

    # gst-examples
    ./ci/run_retry.sh xcodebuild -showBuildSettings -alltargets -project ${EXAMPLES_HOME}/gst-examples/playback/player/ios/GstPlay.xcodeproj $(cat xcode_buildargs)
    ./ci/run_retry.sh xcodebuild -alltargets -destination generic/platform=iOS -project ${EXAMPLES_HOME}/gst-examples/playback/player/ios/GstPlay.xcodeproj $(cat xcode_buildargs)
}

# Run whichever function is asked of us
eval "$1"
