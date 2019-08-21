#!/bin/bash

set -ex

REMOTE=${1:-https://github.com/web-platform-tests/wpt}
REF=${2:-master}

cd ~

if [ ! -d web-platform-tests ]; then
    mkdir web-platform-tests
    cd web-platform-tests

    git init
    git remote add origin ${REMOTE}

    # Initially we just fetch 50 commits in order to save several minutes of fetching
    retry git fetch --quiet --depth=50 --tags origin ${REF}:task_head

    git checkout --quiet task_head
fi
