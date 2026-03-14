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
    elif [[ -n ${CI_MERGE_REQUEST_SOURCE_PROJECT_PATH} ]]; then
        echo "Cerbero merge request, checking for matching branch in user fork of gstreamer"
        user_ns=$(dirname ${CI_MERGE_REQUEST_SOURCE_PROJECT_PATH})
        if user_branch_exists_in "${user_ns}/gstreamer" "${CI_COMMIT_REF_NAME}"; then
            gst_commit="${CI_COMMIT_REF_NAME}"
            gst_remote="${CI_SERVER_URL}/${user_ns}/gstreamer"
            echo "Found branch ${gst_commit} in ${gst_remote}"
        else
            gst_remote="${CI_SERVER_URL}/gstreamer/gstreamer"
        fi
    fi

    # Clone gstreamer repository to get gst-examples and gst-docs
    rm -rf gstreamer
    git clone "${gst_remote}" -b "${gst_commit}" --depth 1 gstreamer/
}

find_textrels() {
    set +x
    local apks
    local libs

    mapfile -t apks < <(find ${EXAMPLES_HOME} -iname '*.apk')
    echo "${apks[@]}"
    if [[ "${#apks[@]}" -eq 0 ]]; then
        echo "No APKs found in ${EXAMPLES_HOME}"
        return 1
    fi

    local ret=0
    for apk in "${apks[@]}"; do
        echo "Checking $apk"
        d=$(basename "${apk}_CONTENTS")
        mkdir "$d"
        unzip -qd "$d" "$apk"
        mapfile -t libs < <(find "$d" -iname libgstreamer_android.so)
        for lib in "${libs[@]}"; do
            echo $lib
            if readelf --dynamic "$lib" | grep TEXTREL; then
                echo "Text relocations found in $lib:"
                scanelf -qT "$lib"
                ret=1
            fi
        done
        rm -rf $d
    done

    if [[ $ret != 0 ]]; then
        echo "ERROR: Text relocations found! See above for details."
    fi
    return $ret
}

build_android_examples() {
    clone_gstreamer
    mkdir -p ${OUTPUT_DIR}

    # extract our binaries
    rm -f gstreamer-1.0-android-universal-*-runtime.tar.*
    mkdir ${GSTREAMER_ROOT_ANDROID}
    time tar -C ${GSTREAMER_ROOT_ANDROID} -xf gstreamer-1.0-android-universal-*.tar.*

    # install tools
    ./ci/run_retry.sh ${ANDROID_HOME}/cmdline-tools/bin/sdkmanager --sdk_root=${ANDROID_HOME} "cmake;3.22.1" "build-tools;35.0.0" "ndk;29.0.14206865" "platforms;android-32"

    # build the examples
    ./ci/generate_rules.py
    CI_BASE_DIR=$PWD
    mv build.ninja ${OUTPUT_DIR}/
    pushd ${OUTPUT_DIR}
    ${CI_BASE_DIR}/ci/run_retry.sh ${ANDROID_HOME}/cmake/3.22.1/bin/ninja

    find_textrels
}

build_ios_examples() {
    # Clone gstreamer repository to get gst-examples and gst-docs
    clone_gstreamer

    # dump some useful information
    xcodebuild -version
    xcodebuild -showsdks
    echo ${XCODE_BUILD_ARGS} > xcode_buildargs

    # extract the xcframework
    rm -rf GStreamer.xcframework
    tar -xvf gstreamer-1.*-xcframework.tar.xz

    local xcodeprojs=(
        # gst-docs ios tutorials
        "gstreamer/subprojects/gst-docs/examples/tutorials/xcode iOS/GStreamer iOS Tutorials.xcodeproj"
        # gst-examples
        "gstreamer/subprojects/gst-examples/playback/player/ios/GstPlay.xcodeproj"
    )
    # TODO: Add "tvOS" "tvOS Simulator" after the next macOS VM image bump
    local destinations=("iOS" "iOS Simulator")

    for xcodeproj in "${xcodeprojs[@]}"; do
        ln -sfn "../../../../../../GStreamer.xcframework" "$(dirname "$xcodeproj")"
        ./ci/run_retry.sh xcodebuild -showBuildSettings -alltargets -project "$xcodeproj" $(cat xcode_buildargs)
        IFS=$'\n' read -r -d '' -a schemes < <(xcodebuild -list -project "$xcodeproj" -json | jq -r '.project.schemes[]' && printf '\0')
        for dest in "${destinations[@]}"; do
            for scheme in "${schemes[@]}"; do
                ./ci/run_retry.sh xcodebuild -scheme "$scheme" -destination generic/platform="${dest}" -project "$xcodeproj" $(cat xcode_buildargs)
            done
        done
    done
}

# Run whichever function is asked of us
eval "$1"
