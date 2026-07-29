# `CMakeLists.txt` の `target_compile_options` 4 OS 重複を CMake function に共通化する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-cmake-compile-options-duplication
- Polished: 2026-07-30

## 目的

`CMakeLists.txt` の `if(TARGET_OS STREQUAL "macos")` から `elseif(TARGET_OS STREQUAL "raspberry-pi-os")` までのブロックで、macos / ubuntu / jetson / raspberry-pi-os の 4 OS にほぼ同一の `target_compile_options` ブロックを記述している。共通部分を CMake function / マクロにまとめて 1 箇所に集約し、「片方だけ変更し忘れる」リスクを解消する。

## 優先度根拠

Medium とする。

- 機能には影響しない構造リファクタだが、4 ブロック繰り返しは「片方だけ変更し忘れる」リスクが高い。
- High ではない理由は、現状のビルドは通っている。
- Low ではない理由は、Broken Windows そのもので、新規プラットフォーム追加時にコピペが量産される。

## 現状

`CMakeLists.txt` の `if(TARGET_OS STREQUAL "macos")` ブロックから `elseif(TARGET_OS STREQUAL "raspberry-pi-os")` ブロックまでの各 OS 分岐 (抜粋):

```cmake
if(TARGET_OS STREQUAL "macos")
  ...
  target_compile_options(sora_sdk_ext
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
  )
  target_compile_options(nanobind-static
    PRIVATE
      "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXX_INCLUDE_DIR}>"
      "$<$<COMPILE_LANGUAGE:CXX>:-isystem${LIBCXXABI_INCLUDE_DIR}>"
  )
elseif(TARGET_OS STREQUAL "ubuntu")
  target_compile_options(sora_sdk_ext PRIVATE ... -nostdinc++ ... -isystem${LIBCXX_INCLUDE_DIR})
  target_compile_options(nanobind-static PRIVATE ... -nostdinc++ ... -isystem${LIBCXX_INCLUDE_DIR} ... -isystem${LIBCXXABI_INCLUDE_DIR})
elseif(TARGET_OS STREQUAL "jetson")
  target_compile_options(sora_sdk_ext PRIVATE ... -nostdinc++ ... -isystem${LIBCXX_INCLUDE_DIR})
  target_compile_options(nanobind-static PRIVATE ... -nostdinc++ ... -isystem${LIBCXX_INCLUDE_DIR} ... -isystem${LIBCXXABI_INCLUDE_DIR})
  ...
elseif(TARGET_OS STREQUAL "raspberry-pi-os")
  target_compile_options(sora_sdk_ext PRIVATE ... -nostdinc++ ... -isystem${LIBCXX_INCLUDE_DIR})
  target_compile_options(nanobind-static PRIVATE ... -nostdinc++ ... -isystem${LIBCXX_INCLUDE_DIR} ... -isystem${LIBCXXABI_INCLUDE_DIR})
```

観察:

1. 4 OS いずれも `sora_sdk_ext` 側には `-nostdinc++` と `-isystem${LIBCXX_INCLUDE_DIR}` の 2 指定、`nanobind-static` 側にはそれに加えて `-isystem${LIBCXXABI_INCLUDE_DIR}` を入れている。すなわち `sora_sdk_ext` 側だけ `LIBCXXABI_INCLUDE_DIR` を入れない非対称が 4 OS で共通している。これが「意図」なのかは CMake 内コメントに書かれていない。
2. macOS の `sora_sdk_ext` には先頭で `set_target_properties(sora_sdk_ext PROPERTIES CXX_VISIBILITY_PRESET hidden)` と `BOOST_ASIO_DISABLE_STD_ATOMIC_WAIT` 定義が追加されている。これは macOS だけの固有設定。
3. raspberry-pi-os の `sora_sdk_ext` には `USE_V4L2=1` 定義と `BUILD_RPATH "\$ORIGIN"` の固有設定が後付けされている。

つまり「`libc++` を nostdinc++ で当てる」共通部分と「OS 固有 (Boost.Asio マクロや V4L2)」固有部分が混在している。

## 設計方針

- 共通部分を CMake function (またはマクロ) として `apply_libcxx_options(target want_libcxxabi)` のように切り出す。引数:
  - `target`: `sora_sdk_ext` または `nanobind-static`
  - `want_libcxxabi`: `LIBCXXABI_INCLUDE_DIR` も渡すか否か (現状 4 OS すべてで sora_sdk_ext は no、nanobind-static は yes)
- `if(NOT TARGET_OS STREQUAL "windows")` のブロックで共通部分を一括適用し、固有部分だけを各 OS 分岐に残す。
- 4 OS 共通の非対称 (`sora_sdk_ext` だけ `LIBCXXABI_INCLUDE_DIR` がない) について、実装時に意図かバグかを再確認する。意図的なら共通化後に CMake コメントを残す。不要な抜けなら共通化のタイミングで `sora_sdk_ext` にも追加する。
  - 検証手段: `sora_sdk_ext` のソースが `libc++abi` のヘッダ (`cxxabi.h` 等) を直接 include しているかを grep で確認する。include していなければ意図的 (不要)、include していればバグ (追加必要) と判定できる。
- 共通化後も、各 OS 固有設定 (Boost.Asio マクロ、`-DUSE_V4L2=1`、`target_link_directories`、`BUILD_RPATH` など) はそのまま各分岐に残す。

## 完了条件

- macOS / ubuntu / jetson / raspberry-pi-os の 4 ブロックで重複していた `target_compile_options(... -nostdinc++ -isystem${LIBCXX_INCLUDE_DIR} ...)` が共通化され、CMake function/macro 1 箇所に集約されていること。
- 4 OS の `sora_sdk_ext` における `LIBCXXABI_INCLUDE_DIR` の扱いについて、「揃える」「揃えない (意図を CMake コメントに残す)」のいずれかが明確になっていること。
- macos / ubuntu / jetson / raspberry-pi-os / windows のいずれでもビルドが通ること。
- 共通化後の CMake が一見して読みやすいこと (function 名・引数名で意図が分かる)。
