#!/bin/bash

# $ /path/to/fix_shared_lib.sh /path/to/sora_sdk.so
# --exclude libcuda.so.1
# --exclude libnvv4l2.so
# ...

set -ex

if [ $# -ne 1 ]; then
  echo "Usage: $0 /path/to/sora_sdk.so"
  exit 1
fi

SOFILE=`realpath $1`
SELF=`realpath $0`

rm -rf fix_shared_lib_tmp
mkdir -p fix_shared_lib_tmp
pushd fix_shared_lib_tmp > /dev/null
  unzip $WHEEL > /dev/null
  echo "`ldd $SOFILE | grep -e '[^ ]* => [^ ]* (.*)'`" | while read name _ path _; do
    if [ "$name" == "" ]; then
      continue
    fi
    echo --exclude $name
    # $SELF $path
  done
popd > /dev/null
rm -rf fix_shared_lib_tmp
