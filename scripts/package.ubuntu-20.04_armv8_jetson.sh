#!/bin/bash

set -ex

cd `dirname $0`/..

WITH_AUDITWHEEL=0
if [ "$1" == "--with-auditwheel" ]; then
  WITH_AUDITWHEEL=1
fi

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
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  curl

curl -sSf https://rye-up.com/get | RYE_INSTALL_OPTION="--yes" bash
. /root/.rye/env

cd /root/sora-python-sdk
rm -rf dist/ wheelhouse/
rye sync
SORA_SDK_TARGET=ubuntu-20.04_armv8_jetson rye run python -m build
'
docker container cp $CONTID:/root/sora-python-sdk/dist/ ./tmp/
if [ $WITH_AUDITWHEEL -ne 0 ]; then
  docker container cp _install/ubuntu-20.04_armv8_jetson/rootfs $CONTID:/root/rootfs
  docker container exec $CONTID /bin/bash -c '
    set -ex

    DEBIAN_FRONTEND=noninteractive apt-get install -y \
      coreutils python3 python3-pip unzip

    pip3 download --only-binary :all: auditwheel
    cp -r *.whl /root/rootfs/

    pushd /root/sora-python-sdk
      rm -rf patchelf
      mkdir -p patchelf
      pushd patchelf
        # Ubuntu 20.04 の patchelf は auditwheel が要求するバージョンを満たしてないので
        # リポジトリから新しいバイナリを取得する
        curl -LO https://github.com/NixOS/patchelf/releases/download/0.14.3/patchelf-0.14.3-aarch64.tar.gz
        tar -xf patchelf-0.14.3-aarch64.tar.gz
      popd
    popd

    cp -r /root/sora-python-sdk /root/rootfs/sora-python-sdk
    rm -rf /root/rootfs/sora-python-sdk/wheelhouse
    chroot /root/rootfs /bin/bash -c '\''
      set -ex
      pip3 install *.whl
      cd /sora-python-sdk
      LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/lib/aarch64-linux-gnu/tegra ./scripts/fix_shared_lib.sh src/sora_sdk/*.so > excludes
      PATH=/sora-python-sdk/patchelf/bin:$PATH auditwheel repair --plat manylinux_2_31_aarch64 dist/*.whl `cat excludes`
    '\''
  '
  docker container cp $CONTID:/root/rootfs/sora-python-sdk/wheelhouse/ ./tmp2/
fi
docker container stop $CONTID
docker container rm $CONTID
mkdir -p dist/
mv tmp/*.whl dist/
rm -rf tmp/
if [ $WITH_AUDITWHEEL -ne 0 ]; then
  mkdir -p wheelhouse/
  mv tmp2/*.whl wheelhouse/
  rm -rf tmp2/
fi