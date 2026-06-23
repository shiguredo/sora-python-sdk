# `find_package(Threads REQUIRED)` を呼んでいるが `Threads::Threads` をリンクしておらず将来のリンクエラー要因になっている問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-cmake-threads-not-linked

## 目的

`CMakeLists.txt:73-75` で Windows 以外の OS について `find_package(Threads REQUIRED)` を要求しているが、いずれのターゲット (`sora_sdk_ext`、`nanobind-static`) にも `Threads::Threads` を明示的にリンクしていない。

現在は `Sora::sora` の transitive 解決で pthread が引かれているため動作しているが、Sora C++ SDK の依存定義が変わったり Sora::sora が PRIVATE で pthread を吸い込んだ瞬間にリンクエラーが顕在化する。意図 (Threads が必要だから REQUIRED) と実装 (どこにも紐付けていない) のずれを解消する。

## 優先度根拠

Medium とする。

- 現在はリンクエラーになっていないが、依存先 (`Sora::sora`) の都合で簡単に壊れる構造的な脆弱性。
- High ではない理由は、現状のビルドは緑のため実害が無い。
- Low ではない理由は、Sora C++ SDK のリビジョン更新時にビルドが突然落ちうるリスクがあり、その時の調査コストを考えると先に直すべき。

## 現状

該当箇所 (`CMakeLists.txt:73-75`):

```cmake
if(NOT TARGET_OS STREQUAL "windows")
  find_package(Threads REQUIRED)
endif()
```

しかし `target_link_libraries` (`CMakeLists.txt:201-202`):

```cmake
target_link_libraries(sora_sdk_ext PRIVATE Sora::sora)
target_link_libraries(nanobind-static PRIVATE Sora::sora)
```

`Threads::Threads` がどこにもない。

CMake の `find_package(Threads REQUIRED)` は import target `Threads::Threads` を生成するだけで、何かに自動でリンクされるわけではない。明示的に `target_link_libraries(<target> Threads::Threads)` する必要がある。

現在ビルドが通っているのは、`Sora::sora` (Sora C++ SDK の CMake config) の interface link libraries に pthread が含まれており、transitive に解決されているため。

## 設計方針

選択肢は 3 つ:

1. **明示リンクする** (推奨)
   ```cmake
   if(NOT TARGET_OS STREQUAL "windows")
     target_link_libraries(sora_sdk_ext PRIVATE Threads::Threads)
   endif()
   ```
   - 意図が明示され、`Sora::sora` の依存変化に左右されない。
   - `find_package(Threads REQUIRED)` の意図と整合する。
2. **`find_package(Threads)` を削除する**
   - 直接 pthread API を呼んでいないなら、`Sora::sora` の transitive に任せる方針。
   - ただし「Sora::sora は pthread を引き続ける」ことに依存する暗黙の前提が残る。
3. 現状維持
   - 推奨しない。意図と実装がずれた状態が残り、将来の謎リンクエラーの種になる。

本 issue では 1 を第一候補とする。`sora_sdk_ext` 側にだけ付ければ十分か、`nanobind-static` 側にも必要かは、`src/` を grep して直接 pthread を使っているかを確認して判断する。

## 完了条件

- `find_package(Threads REQUIRED)` を残すなら `target_link_libraries(sora_sdk_ext PRIVATE Threads::Threads)` (Windows 以外) が CMakeLists.txt に追加されていること。
- 不要と判断した場合は `find_package(Threads REQUIRED)` を削除し、その判断理由を CMake コメントに残すこと。
- 各プラットフォーム (macos / ubuntu / jetson / raspberry-pi-os / windows) でビルドが通ること。
