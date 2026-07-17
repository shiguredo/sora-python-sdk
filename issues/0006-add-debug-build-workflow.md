# scikit-build-core 対応の debug build workflow を追加する

- Priority: Medium
- Created: 2026-05-21
- Updated: 2026-07-17
- Completed: -
- Model: GPT-5
- Branch: feature/add-debug-build-workflow
- Polished: 2026-07-17

## 目的

0001 で削除する旧 `build-debug.yml` を scikit-build-core 前提で再構築し、任意の webrtc-build / sora-cpp-sdk revision を source build した成果物から Sora Python SDK の Debug wheel を生成できるようにする。

release archive を取得する通常の `fetch_deps.cmake` 経路と local source build 経路を明示的に分離し、指定した local 成果物が `CACHE FORCE` で上書きされない契約を追加する。

## 優先度根拠

- 通常の release wheel と publish 経路には影響しないため High ではない。
- Sora C++ SDK / libwebrtc の未リリース修正を Python binding と組み合わせて検証する唯一の CI 経路であり、0001 のマージ後も長期間失ったままにはできないため Medium とする。

## 前提

- 0001 の完了後に実装する。0001 が追加する `cmake/scripts/fetch_deps.cmake`、`_deps/` layout、scikit-build-core 設定を直接変更する。
- 対象は ubuntu-24.04 x86_64 + Python 3.12 / 3.13 / 3.14 の Debug build に限定する。Release / RelWithDebInfo、cross build、publish は扱わない。
- workflow は `workflow_dispatch` だけで起動し、job-level `permissions` は `contents: read` とする。checkout した外部 revision の code を実行するため、secret は渡さない。

## 現状

0001 は setuptools / `run.py` 経路を削除するため、現在の `.github/workflows/build-debug.yml` も削除する。

旧 workflow は次の処理を `run.py build` に委ねている。

- webrtc-build の checkout と `python3 run.py build ubuntu-24.04_x86_64 --debug --no-history`。
- sora-cpp-sdk の checkout と `python3 run.py build ubuntu-24.04_x86_64 --debug --disable-cuda --local-webrtc-build-dir <path>`。
- source build 成果物から `SORA_DIR` / `Boost_ROOT` / `WEBRTC_*` / clang / libc++ / libc++abi の path を算出して Python extension の CMake へ渡す処理。

一方、0001 の `fetch_deps.cmake` は WebRTC / Sora / Boost / LLVM を無条件に取得し、同名の cache 変数を `_deps/` 配下の値へ `CACHE FORCE` で設定する。単に `-DSORA_DIR` / `-DWEBRTC_*` を渡すだけでは local source build 成果物が上書きされる。

## 設計方針

### local dependency mode

`fetch_deps.cmake` に次の cache 変数を追加する。

- `SORA_USE_LOCAL_DEPS`: `BOOL`、既定 `OFF`。
- `SORA_LOCAL_WEBRTC_BUILD_ROOT`: checkout した webrtc-build root の絶対 path。
- `SORA_LOCAL_CPP_SDK_BUILD_ROOT`: checkout した sora-cpp-sdk root の絶対 path。

`SORA_USE_LOCAL_DEPS=ON` は両 root が指定され、`file(REAL_PATH)` 後も指定 root 配下にある次の path が全て実在する場合だけ受け入れる。

| cache 変数 | local source build の path |
| --- | --- |
| `WEBRTC_INCLUDE_DIR` | `<webrtc-root>/_source/ubuntu-24.04_x86_64/webrtc/src` |
| `WEBRTC_LIBRARY_DIR` | `<webrtc-root>/_build/ubuntu-24.04_x86_64/debug/webrtc` |
| `_SORA_CLANG_DIR` | `<webrtc-root>/_source/ubuntu-24.04_x86_64/webrtc/src/third_party/llvm-build/Release+Asserts` |
| `LIBCXX_INCLUDE_DIR` | `<webrtc-root>/_source/ubuntu-24.04_x86_64/webrtc/src/third_party/libc++/src/include` |
| `LIBCXXABI_INCLUDE_DIR` | `<webrtc-root>/_source/ubuntu-24.04_x86_64/webrtc/src/third_party/libc++abi/src/include` |
| `SORA_DIR` | `<sora-root>/_install/ubuntu-24.04_x86_64/debug/sora` |
| `Boost_ROOT` | `<sora-root>/_install/ubuntu-24.04_x86_64/debug/boost` |

各 directory の代表 file も確認する。少なくとも WebRTC library、Sora の CMake package config、Boost header、clang executable、libc++ / libc++abi header が無ければ FATAL_ERROR にする。

local mode では WebRTC / Sora / Boost archive と LLVM の取得、および上表 7 変数の通常値による `CACHE FORCE` を skip する。OpenH264 は通常どおり `DEPS` の Git ref から取得する。入力の一部だけが指定された場合、Debug layout と一致しない場合、path が root 外へ解決された場合は release archive へ fallback せず FATAL_ERROR にする。

通常 build は `SORA_USE_LOCAL_DEPS=OFF` を明示し、従来どおり全 release dependency を取得する。local mode 用 root が設定されていても `OFF` なら参照しない。

### workflow

`.github/workflows/build-debug.yml` を次の構成で新設する。

- `workflow_dispatch` input:
  - `python_sdk_ref`: 未指定時は workflow を起動した commit。
  - `cpp_sdk_ref`: 未指定時は Python SDK の `DEPS` にある `SORA_CPP_SDK_VERSION`。
  - `webrtc_build_ref`: 未指定時は Python SDK の `DEPS` にある `WEBRTC_BUILD_VERSION`。
- matrix: Python 3.12 / 3.13 / 3.14。
- checkout path: `sora-python-sdk` / `sora-cpp-sdk` / `webrtc-build` の 3 directory を分離する。
- 実行順:
  1. 3 checkout の `git rev-parse HEAD` を取得し、input と解決後 commit を job summary へ記録する。
  2. webrtc-build で `python3 run.py build ubuntu-24.04_x86_64 --debug --no-history` を実行する。
  3. sora-cpp-sdk で `python3 run.py build ubuntu-24.04_x86_64 --debug --disable-cuda --local-webrtc-build-dir <webrtc-root>` を実行する。
  4. sora-python-sdk で `uv sync --no-install-project` を実行する。
  5. `SORA_USE_LOCAL_DEPS=ON` と両 root を CMake define へ渡し、`uv build --wheel -Ccmake.build-type=Debug` を実行する。

workflow の shell log は英語、workflow 内のコメントは日本語にする。生成 artifact は `debug-wheel-ubuntu-24.04_x86_64_python-<version>` とし、通常の release workflow はこの prefix を download しない。

### 検証

- `CMakeCache.txt` の `CMAKE_BUILD_TYPE` が `Debug` で、上表 7 変数が checkout 配下の期待 path と一致することを確認する。
- `_deps/ubuntu-24.04_x86_64/.archives/` に WebRTC / Sora / Boost archive が無く、`_deps/llvm/` が生成されていないことを確認する。OpenH264 の取得物は許可する。
- wheel 内 extension の ELF が x86_64 で、`.debug_info` section を持つことを `readelf` で確認する。
- wheel の metadata version と `sora_sdk.__version__` が Python SDK の `VERSION` に一致し、`+debug` を付加しない。
- wheel を clean venv へ install し、`tests/test_version.py` を実行する。

## 完了条件

- workflow_dispatch から未指定 ref の既定値と、3 ref を明示した場合の両方で workflow が green になる。
- Python 3.12 / 3.13 / 3.14 の Debug wheel が生成される。
- 7 dependency path が local checkout 配下に限定され、release archive の WebRTC / Sora / Boost / LLVM を使用しない。
- `SORA_USE_LOCAL_DEPS=OFF` の通常 ubuntu-24.04 x86_64 build が 0001 の dependency fetch / smoke test を維持する。
- 不足 path、root 外 symlink、片方だけの root 指定で configure が失敗し、release dependency へ fallback しない。
- debug artifact が publish / release artifact の取得 pattern に一致しない。

## 解決方法

1. `fetch_deps.cmake` に local dependency mode と path 検証を追加する。
2. 通常 build で同 mode が無効であることを確認する CMake integration test を追加する。
3. `.github/workflows/build-debug.yml` を新設し、外部 2 repository の source build と Debug wheel build を接続する。
4. 全 Python matrix の wheel、CMake cache、ELF、version、install 後 smoke test を検証する。

## ロールバック

問題が local dependency mode に限定される場合は forward fix を優先する。根本設計に問題があり revert する場合は 0006 の squash commit を `git revert <squash-commit>` し、通常 build が 0001 の release dependency 経路だけで green になることを確認する。debug artifact は外部公開しないため、PyPI / GitHub Release の回収は発生しない。
