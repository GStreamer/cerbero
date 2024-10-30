#!/bin/sh
# vim: set sts=2 sw=2 et :
#
# Takes a branch name and a repo name, and returns 0 if that branch exists in
# a fork of the repo in the user's namespace, else returns non-zero.

quoted() {
  python3 -c "import urllib.parse; print(urllib.parse.quote('$1', safe=''))"
}

PROJECT_PATH=$(quoted "$1")
BRANCH_NAME=$(quoted "$2")

if [[ -z ${PROJECT_PATH} ]] || [[ -z ${BRANCH_NAME} ]]; then
  echo "Usage: $0 <namespace/repo_name> <branch_name>"
  exit 1
fi

curl --fail-with-body -s "${CI_API_V4_URL}/projects/${PROJECT_PATH}/repository/branches/${BRANCH_NAME}"
