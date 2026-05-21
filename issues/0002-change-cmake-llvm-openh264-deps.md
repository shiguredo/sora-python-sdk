# CMake による LLVM と OpenH264 の deps 取得

- Priority: High
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-cmake-llvm-openh264-deps

## 目的

0001 で CMake に移した deps 取得に、現 `buildbase.py` の `install_llvm` と `install_openh264` 相当を追加する。Linux / macOS ネイティブビルドで libwebrtc 付属 clang / libc++ と OpenH264 ヘッダが CMake 内で利用可能になる。

## 優先度根拠

High。0001 単体では ubuntu x86_64 でも libwebrtc clang / `-nostdinc++` が必要なため、ネイティブ Linux ビルドの完了に必須。

## 現状

- `install_llvm` は WebRTC 展開後の `VERSIONS` / `DEPS` を読み、tools / libc++ / buildtools を git shallow clone し `update.py` で clang を取得する
- `install_openh264` は git shallow clone + `make install-headers` でヘッダのみ配置する
- いずれも `@versioned` デコレータで `*.version` ファイルによるキャッシュを行う
- Windows では OpenH264 ヘッダを手動コピーする

## 設計方針

- WebRTC DL 完了後に LLVM 取得を実行する（`add_dependencies` で順序保証）
- LLVM は `cmake/scripts/install_llvm.sh` または `cmake/Scripts/fetch_llvm.cmake` に移植する
- OpenH264 は `ExternalProject` git shallow または script で `_deps/${SORA_PLATFORM}/openh264/` に配置する
- キャッシュは webcodecs-py 同様 `if(EXISTS ...)` + stamp で行う
- `buildbase.py` の `install_llvm` / `install_openh264` は 0006 で削除する

## 完了条件

- `ubuntu-24.04_x86_64` ネイティブで libwebrtc clang / libc++ パスが CMake から解決される
- OpenH264 ヘッダが `_deps/` 配下に配置され、`dynamic_h264_*.cpp` がビルドできる
- macOS ネイティブでも同様に LLVM deps が取得できる
- `uv build --wheel` が 0001 比で追加設定なし（または env のみ）で成功する

## 解決方法

- `cmake/scripts/install_llvm.sh` を新設し、`buildbase.py` L1187–1233 の処理を移植する
- OpenH264 用 `ExternalProject` または script を `CMakeLists.txt` に追加する
- `CMakeLists.txt` の compiler / include 設定を `_deps/` パス参照に更新する
- 0001 の ubuntu x86_64 ネイティブビルドで検証する
