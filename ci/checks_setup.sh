#! /bin/bash

set -e

python3 -m pip install pre-commit
echo "Pre-commit home": $PRE_COMMIT_HOME
mkdir $PRE_COMMIT_HOME
pre-commit install-hooks