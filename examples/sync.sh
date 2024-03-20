#!/bin/bash

# ローカルインストールしたキャッシュを削除した上で rye sync するスクリプト。
#
# `rye add sora_sdk --path <sora_sdk_dir>` でローカルで書き換えた sora-python-sdk を
# 利用可能だが、キャッシュが残っていると一生更新されないため、キャッシュディレクトリを削除する。
#
# 毎回どこのディレクトリを消せばいいか忘れてしまうので、このスクリプトで対応する。

set -ex

case "`uname`" in
  "Darwin" ) CACHE_DIR=~/Library/Caches/pip ;;
  "Linux" ) CACHE_DIR=~/.cache/pip ;;
  * ) exit 1 ;;
esac

rm -rf $CACHE_DIR/wheels
rye sync
