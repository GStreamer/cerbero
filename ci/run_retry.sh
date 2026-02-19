#!/bin/bash
# vim: set sts=4 sw=4 et :

set -o pipefail

ERRORS=(
    "Warning: An error occurred while preparing SDK package Android SDK Tools: Connection reset."
    "The Xcode build system has crashed. Build again to continue."
    "libc++abi: terminating with uncaught exception"
    # https://github.com/rust-lang/rust/issues/127883#issuecomment-2290594194
    "Access is denied (os error 5)"
    "LINK : fatal error LNK1104: cannot open file"
    # Mono on Wine is flaky
    "ShellExecuteEx failed"
    # crates.io flakiness
    "warning: spurious network error"
    # Weird xcode toolchain bug 
    "otool: unknown char"
    # Wine is flaky
    "The explorer process failed to start."
    # Mac Virtualization bugs where lipo/git etc are spawned instead of clang
    "lipo: unknown flag: -I"
    "unknown option: -I"
    # Random permission errors with g-ir-scanner and other tools that write
    # temporary files on Windows
    "PermissionError: [Errno 13] Permission denied:"
)
ERROR_RETRIES=3
if [[ $(uname) =~ MINGW* ]]; then
    WIN32_RETRIES=3
else
    WIN32_RETRIES=0
fi
LOGFILE="/tmp/logfile.txt"

while true; do
    spurious_error=
    "$@" | tee "$LOGFILE" 2>&1
    ret=$?
    [[ $ret == 0 ]] && break
    while read line; do
        for error in "${ERRORS[@]}"; do
            if [[ "$line" =~ "$error" ]]; then
                spurious_error=$line
                break 2
            fi
        done
    done < "$LOGFILE"
    rm -f "$LOGFILE"
    if [[ -n $spurious_error ]]; then
        if [[ $ERROR_RETRIES == 0 ]]; then
            echo "Exiting with code $ret on persistent spurious error: $spurious_error"
            exit $ret
        fi
        echo "Exit code $ret: retrying, caught spurious failure: $spurious_error"
        ERROR_RETRIES=$((ERROR_RETRIES-1))
    elif [[ $WIN32_RETRIES == 0 ]]; then
        echo "Exiting with code $ret on unknown error"
        exit $ret
    else
        echo "Exit code $ret: retrying, possibly a random failure on win32"
        WIN32_RETRIES=$((WIN32_RETRIES-1))
    fi
done
