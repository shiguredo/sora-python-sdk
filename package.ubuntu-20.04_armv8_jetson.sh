#!/bin/bash

set -ex

cd `dirname $0`

CONTID=`docker container create -it arm64v8/ubuntu:20.04`
docker container start $CONTID
docker container exec $CONTID mkdir -p /root/sora-python-sdk
for file in `echo *`; do
  if [ "${file:0:1}" == "_" ]; then
    continue
  fi
  docker container cp $file $CONTID:/root/sora-python-sdk/$file
done
docker container exec $CONTID /bin/bash -c '
set -ex

apt-get update
apt-get install -y \
  curl

curl -sSf https://rye-up.com/get | RYE_INSTALL_OPTION="--yes" bash
. "/root/.rye/env"

cd /root/sora-python-sdk
rm -rf dist/
rye sync
rye run python -m build
'
docker container cp $CONTID:/root/sora-python-sdk/dist/ ./tmp/
docker container stop $CONTID
docker container rm $CONTID
mkdir -p dist/
mv tmp/*.whl dist/
rm -rf tmp/