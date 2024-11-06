#!/bin/bash

set -ex

show_ccache_sum() {
    if [[ -n ${HAVE_CCACHE} ]]; then
        ccache -s
    fi
}

# Print the working directory in the native OS path format, but with forward
# slashes
pwd_native() {
    if [[ -n "$MSYSTEM" ]]; then
        cygpath -m "$(pwd)"
    else
        pwd
    fi
}

fix_build_tools() {
    if [[ $(uname) == Darwin ]]; then
        # Bison needs these env vars set for the build-tools prefix to be
        # relocatable, and we only build it on macOS. On Linux we install it
        # using the package manager, and on Windows we use the MSYS Bison.
        export M4="$(pwd)/${CERBERO_HOME}/build-tools/bin/m4"
        export BISON_PKGDATADIR="$(pwd)/${CERBERO_HOME}/build-tools/share/bison"
    fi
}

user_branch_exists_in() {
    ./ci/exists_branch_in_user_repo.sh "$1" "$2"
}

# Produces runtime and devel tarball packages for linux/android or .pkg for macos
cerbero_package_and_check() {
    # Plugins that dlopen libs and will have 0 features on the CI, and hence
    # won't be listed in `gst-inspect-1.0` output, and have to be inspected
    # explicitly
    local dlopen_plugins=(jack soup adaptivedemux2)
    if [[ $CONFIG = win* ]]; then
        dlopen_plugins+=(amfcodec mediafoundation msdk nvcodec qsv)
    elif [[ $CONFIG = linux* ]]; then
        dlopen_plugins+=(msdk nvcodec qsv va vaapi)
    fi

    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS package --offline ${CERBERO_PACKAGE_ARGS} -o "$(pwd_native)" gstreamer-1.0

    # Run gst-inspect-1.0 for some basic checks. Can't do this for cross-(android|ios)-universal, of course.
    if [[ $CONFIG != *ios-universal* ]] && [[ $CONFIG != *android-universal* ]] && [[ $CONFIG != *cross-win* ]]; then
        $CERBERO $CERBERO_ARGS run gst-inspect-1.0$CERBERO_RUN_SUFFIX --version
        $CERBERO $CERBERO_ARGS run gst-inspect-1.0$CERBERO_RUN_SUFFIX
        for plugin in $dlopen_plugins; do
            $CERBERO $CERBERO_ARGS run gst-inspect-1.0$CERBERO_RUN_SUFFIX $plugin
        done
    fi

    show_ccache_sum
}

cerbero_before_script() {
    # Default: unset, use recipe defaults
    local gst_commit
    local gst_remote
    local gstpluginsrs_commit
    local gstpluginsrs_remote
    pwd
    ls -lha

    # Three special cases in which we should build against a user-specific
    # branch of gstreamer or gst-plugins-rs:
    # 1. We have been triggered by gstreamer monorepo CI
    #    - ci/gitlab/trigger_cerbero_pipeline.py
    # 2. We have been triggered by gst-plugins-rs CI
    #    - ci/cerbero/trigger_cerbero_pipeline.py
    # 3. We are running as part of CI for a cerbero merge request
    if [[ -n ${CI_GSTREAMER_PATH} ]]; then
        echo "gstreamer trigger CI, using MR user branch"
        gst_commit="${CI_GSTREAMER_REF_NAME}"
        gst_remote="${CI_SERVER_URL}/${CI_GSTREAMER_PATH}"
    elif [[ -n ${CI_GST_PLUGINS_RS_PATH} ]]; then
        echo "gst-plugins-rs trigger CI, using MR user branch"
        gstpluginsrs_commit="${CI_GST_PLUGINS_RS_REF_NAME}"
        gstpluginsrs_remote="${CI_SERVER_URL}/${CI_GST_PLUGINS_RS_PATH}"
    elif [[ ${CI_PROJECT_NAMESPACE} != gstreamer ]]; then
        echo "Cerbero merge request, checking for matching branches in user forks of gstreamer and gst-plugins-rs"
        if user_branch_exists_in "${CI_PROJECT_NAMESPACE}/gstreamer" "${CI_COMMIT_REF_NAME}"; then
            gst_commit="${CI_COMMIT_REF_NAME}"
            gst_remote="${CI_SERVER_URL}/${CI_PROJECT_NAMESPACE}/gstreamer"
            echo "Found gstreamer branch ${gst_commit} in ${gst_remote}"
        fi
        if user_branch_exists_in "${CI_PROJECT_NAMESPACE}/gst-plugins-rs" "${CI_COMMIT_REF_NAME}"; then
            gstpluginsrs_commit="${CI_COMMIT_REF_NAME}"
            gstpluginsrs_remote="${CI_SERVER_URL}/${CI_PROJECT_NAMESPACE}/gst-plugins-rs"
            echo "Found gst-plugins-rs branch ${gstpluginsrs_commit} in ${gstpluginsrs_remote}"
        fi
    fi

    # If there's no cerbero-sources directory in the runner cache, copy it from
    # the image cache
    if ! [[ -d ${CERBERO_SOURCES} ]]; then
        time cp -a "${CERBERO_HOST_DIR}/${CERBERO_SOURCES}" .
    fi
    du -sch "${CERBERO_SOURCES}" || true

    echo "home_dir = \"$(pwd_native)/${CERBERO_HOME}\"" > localconf.cbc
    echo "local_sources = \"$(pwd_native)/${CERBERO_SOURCES}\"" >> localconf.cbc
    echo "mingw_perl_prefix = \"${CERBERO_HOST_DIR}/${CERBERO_HOME}/mingw/perl\"" >> localconf.cbc
    if [[ $CONFIG == win??.cbc ]] || [[ $CONFIG =~ uwp ]] ; then
        # Visual Studio 2022 build tools install path
        echo 'vs_install_path = "C:/BuildTools"' >> localconf.cbc
        echo 'vs_install_version = "vs17"' >> localconf.cbc
    fi
    if [[ "x${FDO_CI_CONCURRENT}" != "x" ]]; then
        echo "num_of_cpus = ${FDO_CI_CONCURRENT}" >> localconf.cbc
    fi

    echo "recipes_commits = {" >> localconf.cbc
    if [[ -n $gst_commit ]]; then
        echo "  'gstreamer-1.0': 'ci/${gst_commit}'," >> localconf.cbc
    fi
    if [[ -n $gstpluginsrs_commit ]]; then
        echo "  'gst-plugins-rs-1.0': 'ci/${gstpluginsrs_commit}'," >> localconf.cbc
    fi
    echo "}" >> localconf.cbc

    echo "recipes_remotes = {" >> localconf.cbc
    if [[ -n $gst_remote ]]; then
        echo "  'gstreamer-1.0': {'ci': '${gst_remote}'}," >> localconf.cbc
    fi
    if [[ -n $gstpluginsrs_remote ]]; then
        echo "  'gst-plugins-rs-1.0': {'ci': '${gstpluginsrs_remote}'}," >> localconf.cbc
    fi
    echo "}" >> localconf.cbc

    cat localconf.cbc

    # GitLab runner does not always wipe the image after each job, so do that
    # to ensure we don't have any leftover data from a previous job such as
    # a dirty builddir, or tarballs/pkg files, leftover files from an old
    # cerbero commit, etc. Skip the things we actually need to keep.
    time git clean -xdf -e localconf.cbc -e "${CERBERO_SOURCES}"
}

cerbero_script() {
    show_ccache_sum

    $CERBERO $CERBERO_ARGS show-config
    $CERBERO $CERBERO_ARGS fetch-bootstrap --jobs=4
    $CERBERO $CERBERO_ARGS fetch-package --jobs=4 --deps gstreamer-1.0
    du -sch "${CERBERO_SOURCES}" || true

    local project
    if [[ -n $CI_GST_PLUGINS_RS_REF_NAME ]]; then
        project="gst-plugins-rs"
    else
        project="gstreamer"
    fi
    $CERBERO $CERBERO_ARGS fetch-cache --branch "${GST_UPSTREAM_BRANCH}" --project "${project}"

    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS bootstrap --offline --system=$CERBERO_BOOTSTRAP_SYSTEM --assume-yes
    fix_build_tools

    cerbero_package_and_check
}

upload_cache() {
    # Check that the env var is set. Don't expand this protected variable by
    # doing something silly like [[ -n ${CERBERO_...} ]] because it will get
    # printed in the CI logs due to set -x
    if env | grep -q -e CERBERO_PRIVATE_SSH_KEY; then
        # Don't generate and upload caches for scheduled pipelines on main branch
        if [[ "x${CI_PIPELINE_SOURCE}" != "xschedule" ]]; then
            time $CERBERO $CERBERO_ARGS gen-cache \
                --project="$1" --branch "${GST_UPSTREAM_BRANCH}"
            time $CERBERO $CERBERO_ARGS upload-cache \
                --project="$1" --branch "${GST_UPSTREAM_BRANCH}"
        fi
    fi
}

cerbero_deps_script() {
    # Build deps for all gstreamer recipes and any recipes that build gstreamer
    # plugins (and hence compile against gstreamer)
    local build_deps="gstreamer-1.0 gst-plugins-base-1.0 gst-plugins-good-1.0
        gst-plugins-bad-1.0 gst-plugins-ugly-1.0 gst-rtsp-server-1.0
        gst-devtools-1.0 gst-editing-services-1.0 libnice gst-plugins-rs"
    # Deps that don't get picked up automatically because are only listed in
    # the package files
    local more_deps="glib-networking"
    # UWP target doesn't support building ffmpeg yet
    if ! [[ $CONFIG =~ uwp ]]; then
        build_deps="$build_deps gst-libav-1.0"
        # Deps that don't get picked up automatically because they are
        # a runtime dep
        if [[ $ARCH =~ darwin|msvc|mingw ]]; then
            more_deps="$more_deps pkg-config"
        fi
    fi

    show_ccache_sum

    $CERBERO $CERBERO_ARGS show-config
    $CERBERO $CERBERO_ARGS fetch-bootstrap --jobs=4
    $CERBERO $CERBERO_ARGS fetch-package --jobs=4 --deps gstreamer-1.0
    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS bootstrap --offline --system=$CERBERO_BOOTSTRAP_SYSTEM --assume-yes
    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS build-deps --offline $build_deps
    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS build --offline $more_deps
    # All external deps have been built, upload the cache for the cerbero CI
    # triggered by the gstreamer monorepo
    upload_cache gstreamer

    # Now, build everything except gst-plugins-rs and gst-android-1.0 since
    # that also pulls gst-plugins-rs in
    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS package --offline gstreamer-1.0 --only-build-deps \
            --exclude gst-plugins-rs --exclude gst-android-1.0 --exclude gstreamer-ios-templates
    upload_cache gst-plugins-rs

    cerbero_package_and_check
}

# Run whichever function is asked of us
eval "$1"
