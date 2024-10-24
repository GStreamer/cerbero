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
    local gst_user_branch=
    local gstrs_user_branch=
    pwd
    ls -lha

    if [[ -n ${CI_COMMIT_REF_NAME} ]] && [[ ${CI_COMMIT_REF_NAME} != ${GST_UPSTREAM_BRANCH} ]]; then
        local ci_project_ns_url="${CI_SERVER_URL}/${CI_PROJECT_NAMESPACE}"
        if user_branch_exists_in gstreamer "${CI_COMMIT_REF_NAME}"; then
            gst_user_branch=1
        fi
        if user_branch_exists_in gst-plugins-rs "${CI_COMMIT_REF_NAME}"; then
            gstrs_user_branch=1
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

    # These vars are set for pipelines via trigger_cerbero_pipeline.py in
    # gstreamer and gst-plugins-rs CI
    echo "recipes_commits = {" >> localconf.cbc
    if [[ -n $gst_user_branch ]]; then
        echo "  'gstreamer-1.0': 'ci/${CI_COMMIT_REF_NAME}'," >> localconf.cbc
    else
        echo "  'gstreamer-1.0': 'ci/${CI_GSTREAMER_REF_NAME}'," >> localconf.cbc
    fi
    if [[ -n $CI_GST_PLUGINS_RS_REF_NAME ]]; then
        echo "  'gst-plugins-rs-1.0': 'ci/${CI_GST_PLUGINS_RS_REF_NAME}'," >> localconf.cbc
    elif [[ -n $gstrs_user_branch ]]; then
        echo "  'gst-plugins-rs-1.0': 'ci/${CI_COMMIT_REF_NAME}'," >> localconf.cbc
    fi
    echo "}" >> localconf.cbc

    echo "recipes_remotes = {" >> localconf.cbc

    # Add gstreamer monorepo remote
    if [[ -n $gst_user_branch ]]; then
        echo "  'gstreamer-1.0': {'ci': '${ci_project_ns_url}/gstreamer'}," >> localconf.cbc
    else
        echo "  'gstreamer-1.0': {'ci': '${CI_GSTREAMER_URL}'}," >> localconf.cbc
    fi

    # Add gst-plugins-rs remote
    if [[ -n $CI_GST_PLUGINS_RS_URL ]]; then
        echo "  'gst-plugins-rs-1.0': {'ci': '${CI_GST_PLUGINS_RS_URL}'}," >> localconf.cbc
    elif [[ -n $gstrs_user_branch ]]; then
        echo "  'gst-plugins-rs-1.0': {'ci': '${ci_project_ns_url}/gst-plugins-rs'}," >> localconf.cbc
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

    $CERBERO $CERBERO_ARGS fetch-cache --branch "${GST_UPSTREAM_BRANCH}"

    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS bootstrap --offline --system=$CERBERO_BOOTSTRAP_SYSTEM
    fix_build_tools

    cerbero_package_and_check
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
    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS bootstrap --offline --system=$CERBERO_BOOTSTRAP_SYSTEM
    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS build-deps --offline $build_deps
    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS build --offline $more_deps

    # Check that the env var is set. Don't expand this protected variable by
    # doing something silly like [[ -n ${CERBERO_...} ]] because it will get
    # printed in the CI logs due to set -x
    if env | grep -q -e CERBERO_PRIVATE_SSH_KEY; then
        # Don't generate and upload caches for scheduled pipelines on main branch
        if [[ "x${CI_PIPELINE_SOURCE}" != "xschedule" ]]; then
            time $CERBERO $CERBERO_ARGS gen-cache --branch "${GST_UPSTREAM_BRANCH}"
            time $CERBERO $CERBERO_ARGS upload-cache --branch "${GST_UPSTREAM_BRANCH}"
        fi
    fi

    cerbero_package_and_check
}

# Run whichever function is asked of us
eval "$1"
