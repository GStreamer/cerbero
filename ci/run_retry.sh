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
)
RETRIES=3
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
    if [[ $spurious_error == '' ]] || [[ $RETRIES == 0 ]]; then
        exit $ret
    fi
    RETRIES=$((RETRIES-1))
    echo "Retrying, caught spurious failure: $spurious_error"
done
