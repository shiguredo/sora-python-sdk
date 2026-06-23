# `CMakeLists.txt` の `target_compile_options` 4 OS 重複と macOS sora_sdk_ext の `LIBCXXABI_INCLUDE_DIR` 抜けを解消する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-cmake-compile-options-duplication

## 目的

`CMakeLists.txt:121-171` で macos / ubuntu / jetson / raspberry-pi-os の 4 OS にほぼ同一の `target_compile_options` ブロックを記述している。重複の中で、macOS の `sora_sdk_ext` 側だけ `LIBCXXABI_INCLUDE_DIR` の `-isystem` 指定が抜けている (`nanobind-static` 側には入っている) という非対称が紛れ込んでおり、これがバグなのか意図なのか読み取れない。

共通部分を CMake function / マクロにまとめて 1 箇所に集約し、ついでに macOS の差異が意図かバグかを明確にする。

## 優先度根拠

Medium とする。

- 機能には影響しない構造リファクタだが、4 ブロック繰り返しは「片方だけ変更し忘れる」リスクが高い (実際に macOS の sora_sdk_ext で `LIBCXXABI_INCLUDE_DIR` が抜けている)。
- High ではない理由は、現状のビルドは通っている。
- Low ではない理由は、Broken Windows そのもので、新規プラットフォーム追加時にコピペが量産される。

## 現状

`CMakeLists.txt:121-171` の各 OS 分岐 (抜粋):

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

1. 4 OS いずれも `sora_sdk_ext` 側には `-nostdinc++` と `-isystem${LIBCXX_INCLUDE_DIR}` の 2 指定、`nanobind-static` 側にはそれに加えて `-isystem${LIBCXXABI_INCLUDE_DIR}` を入れている。すなわち sora_sdk_ext 側だけ `LIBCXXABI_INCLUDE_DIR` を入れない非対称が 4 OS で共通している。これが「意図」なのかは CMake 内コメントに書かれていない。
2. macOS の sora_sdk_ext には先頭で `set_target_properties(sora_sdk_ext PROPERTIES CXX_VISIBILITY_PRESET hidden)` と `BOOST_ASIO_DISABLE_STD_ATOMIC_WAIT` 定義が追加されている。これは macOS だけの固有設定。
3. raspberry-pi-os の sora_sdk_ext には `USE_V4L2=1` 定義と `BUILD_RPATH "\$ORIGIN"` の固有設定が後付けされている。

つまり「`libc++` を nostdinc++ で当てる」共通部分と「OS 固有 (Boost.Asio マクロや V4L2)」固有部分が混在している。

## 設計方針

- 共通部分を CMake function (またはマクロ) として `apply_libcxx_options(target want_libcxxabi)` のように切り出す。引数:
  - `target`: `sora_sdk_ext` または `nanobind-static`
  - `want_libcxxabi`: `LIBCXXABI_INCLUDE_DIR` も渡すか否か (現状 sora_sdk_ext は no、nanobind-static は yes)
- `if(TARGET_OS STREQUAL "macos" OR TARGET_OS STREQUAL "ubuntu" OR TARGET_OS STREQUAL "jetson" OR TARGET_OS STREQUAL "raspberry-pi-os")` のような大きな OR ブロックで共通部分を一括適用し、固有部分だけを各 elseif に残す。
- macOS の sora_sdk_ext が `LIBCXXABI_INCLUDE_DIR` を入れていない理由を実装時に再確認する。意図的なら共通化後にコメントを残す。不要な抜けなら共通化のタイミングで他 OS と同等に揃える。
  - 仮説: sora_sdk_ext の sources は `LIBCXXABI` のヘッダを直接 include しないため不要、nanobind 側はテンプレートで触れるため必要、という整理がありうるが、現コードには根拠が書かれていない。
- 共通化後も、各 OS 固有設定 (Boost.Asio マクロ、`-DUSE_V4L2=1`、`target_link_directories`、`BUILD_RPATH` など) はそのまま各分岐に残す。

## 完了条件

- macOS / ubuntu / jetson / raspberry-pi-os の 4 ブロックで重複していた `target_compile_options(... -nostdinc++ -isystem${LIBCXX_INCLUDE_DIR} ...)` が共通化され、CMake function/macro 1 箇所に集約されていること。
- macOS の sora_sdk_ext における `LIBCXXABI_INCLUDE_DIR` の扱いについて、「揃える」「揃えない (意図を CMake コメントに残す)」のいずれかが明確になっていること。
- macos / ubuntu / jetson / raspberry-pi-os / windows のいずれでもビルドが通ること。
- 共通化後の CMake が一見して読みやすいこと (function 名・引数名で意図が分かる)。
