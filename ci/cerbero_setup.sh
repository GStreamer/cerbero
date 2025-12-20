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

    if [[ $CONFIG = win* ]] || [[ $CONFIG = *macos* ]]; then
        ./ci/run_retry.sh $CERBERO $CERBERO_ARGS package --offline --artifact wheel -o "$(pwd_native)" gstreamer-1.0
    fi

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

# Using "main" as the branch name in the Cerbero PR's fork is valid,
# and in that case we should NOT look for a branch by the same name in
# the user's gstreamer / gst-plugins-rs forks because those will always
# exist and the user doesn't intend for us to use that outdated branch
#
# We also don't want to search for a stable branch name, such as 1.24
can_search_branch_name() {
    [[ $1 != main ]] && [[ $1 != ${GST_UPSTREAM_BRANCH} ]]
}

cerbero_before_script() {
    # Default: unset, use recipe defaults
    local gst_commit
    local gst_remote
    local gstpluginsrs_commit
    local gstpluginsrs_remote
    local user_branch
    local user_ns
    local job_type="other"
    pwd
    ls -lha


    # Three special cases in which we should build against a user-specific
    # branch of gstreamer or gst-plugins-rs:
    # 1. We have been triggered by gstreamer monorepo MR CI
    #    - ci/gitlab/trigger_cerbero_pipeline.py
    #    - job_type=gstreamer-mr
    # 2. We have been triggered by gst-plugins-rs MR CI
    #    - ci/cerbero/trigger_cerbero_pipeline.py
    #    - job_type=gstpluginsrs-mr
    # 3. We are running as part of CI for a cerbero merge request
    #    - job_type=cerbero-mr
    #
    # We should skip that logic when:
    # * We are running in post-merge CI pipeline
    # * We are running in a scheduled pipeline
    # job_type=other
    if [[ -n ${CI_GSTREAMER_PATH} ]]; then
        echo "gstreamer MR trigger CI"
        job_type="gstreamer-mr"
        if can_search_branch_name ${CI_GSTREAMER_REF_NAME}; then
            echo "Using gstreamer MR user branch"
            gst_commit="${CI_GSTREAMER_REF_NAME}"
            gst_remote="${CI_SERVER_URL}/${CI_GSTREAMER_PATH}"
            user_branch="${CI_GSTREAMER_REF_NAME}"
            user_ns=$(dirname ${CI_GSTREAMER_PATH})
        fi
    elif [[ -n ${CI_GST_PLUGINS_RS_PATH} ]]; then
        echo "gst-plugins-rs MR trigger CI"
        job_type="gstpluginsrs-mr"
        if can_search_branch_name ${CI_GST_PLUGINS_RS_REF_NAME}; then
            echo "Using gst-plugins-rs MR user branch"
            gstpluginsrs_commit="${CI_GST_PLUGINS_RS_REF_NAME}"
            gstpluginsrs_remote="${CI_SERVER_URL}/${CI_GST_PLUGINS_RS_PATH}"
            user_branch="${CI_GST_PLUGINS_RS_REF_NAME}"
            user_ns=$(dirname ${CI_GST_PLUGINS_RS_PATH})
        fi
    elif [[ -n ${CI_MERGE_REQUEST_SOURCE_PROJECT_PATH} ]]; then
        echo "Cerbero merge request"
        job_type="cerbero-mr"
        if can_search_branch_name ${CI_COMMIT_REF_NAME}; then
            echo "Using cerbero MR user branch"
            user_branch=${CI_COMMIT_REF_NAME}
            user_ns=$(dirname ${CI_MERGE_REQUEST_SOURCE_PROJECT_PATH})
        fi
    fi

    # Search for the specific branch in the user's forks
    if [[ -n $user_branch ]]; then
        # If we're in a gst-plugins-rs MR or a cerbero MR, look for a matching
        # monorepo branch in the user's fork
        if [[ $job_type = "gstpluginsrs-mr" ]] || [[ $job_type = "cerbero-mr" ]]; then
            if user_branch_exists_in "${user_ns}/gstreamer" "${user_branch}"; then
                gst_commit="${user_branch}"
                gst_remote="${CI_SERVER_URL}/${user_ns}/gstreamer"
                echo "Found gstreamer branch ${gst_commit} in ${gst_remote}"
            fi
        fi
        # If we're in a gstreamer monorepo MR or a cerbero MR, look for
        # a matching gst-plugins-rs branch in the user's fork
        if [[ $job_type = "gstreamer-mr" ]] || [[ $job_type = "cerbero-mr" ]]; then
            if user_branch_exists_in "${user_ns}/gst-plugins-rs" "${user_branch}"; then
                gstpluginsrs_commit="${user_branch}"
                gstpluginsrs_remote="${CI_SERVER_URL}/${user_ns}/gst-plugins-rs"
                echo "Found gst-plugins-rs branch ${gstpluginsrs_commit} in ${gstpluginsrs_remote}"
            fi
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
    if [[ $CONFIG = win* ]] || [[ $CONFIG = cross-win-* ]] ; then
        # Evade PATH_MAX
        echo "sources = f'{home_dir}/s'" >> localconf.cbc
    fi
    if [[ "x${FDO_CI_CONCURRENT}" != "x" ]]; then
        echo "num_of_cpus = ${FDO_CI_CONCURRENT}" >> localconf.cbc
    fi

    echo "recipes_commits = {" >> localconf.cbc
    if [[ -n $gst_commit ]]; then
        echo "  'gstreamer-1.0': 'ci/${gst_commit}'," >> localconf.cbc
    fi
    if [[ -n $gstpluginsrs_commit ]]; then
        echo "  'gst-plugins-rs': 'ci/${gstpluginsrs_commit}'," >> localconf.cbc
    fi
    echo "}" >> localconf.cbc

    echo "recipes_remotes = {" >> localconf.cbc
    if [[ -n $gst_remote ]]; then
        echo "  'gstreamer-1.0': {'ci': '${gst_remote}'}," >> localconf.cbc
    fi
    if [[ -n $gstpluginsrs_remote ]]; then
        echo "  'gst-plugins-rs': {'ci': '${gstpluginsrs_remote}'}," >> localconf.cbc
    fi
    echo "}" >> localconf.cbc

    cat localconf.cbc

    # GitLab runner does not always wipe the image after each job, so do that
    # to ensure we don't have any leftover data from a previous job such as
    # a dirty builddir, or tarballs/pkg files, leftover files from an old
    # cerbero commit, etc. Skip the things we actually need to keep.
    time git clean -xdf -e localconf.cbc -e "${CERBERO_SOURCES}"
}

cerbero_bootstrap() {
    $CERBERO $CERBERO_ARGS fetch-bootstrap --jobs=4
    ./ci/run_retry.sh $CERBERO $CERBERO_ARGS bootstrap --offline --system=$CERBERO_BOOTSTRAP_SYSTEM --assume-yes
}

cerbero_test() {
    $CERBERO $CERBERO_ARGS show-config
    cerbero_bootstrap
}

cerbero_script() {
    show_ccache_sum

    $CERBERO $CERBERO_ARGS show-config | tee config.txt
    if [[ -n $CI_GST_PLUGINS_RS_REF_NAME ]] && grep -q '\<rust : False\>' config.txt; then
        echo "gst-plugins-rs trigger CI, but Rust variant is disabled. Skipping job."
        return 0
    fi

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
