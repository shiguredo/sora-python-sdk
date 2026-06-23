# Jetson ビルドで RPATH 設定が無く実機での共有ライブラリ解決が環境依存になる問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-jetson-no-rpath

## 目的

`CMakeLists.txt` の Jetson 向け分岐 (`TARGET_OS STREQUAL "jetson"`) は `${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/{tegra,nvidia}` を `target_link_directories` で指定しているが、ビルド成果物に `BUILD_RPATH` / `INSTALL_RPATH` を設定していない。
その結果、リンク時はライブラリを解決できても、実機で `import sora_sdk` する際に `libnvbuf_*.so` などの Tegra / NVIDIA 共有ライブラリを動的リンカが見つけられず、ユーザー側で `LD_LIBRARY_PATH` を手当てしないと ImportError になる経路がある。
同じファイル内の `raspberry-pi-os` 分岐は `set_target_properties(sora_sdk_ext PROPERTIES BUILD_RPATH "\$ORIGIN")` を明示的に設定しており、Jetson だけがこの扱いから抜けている。
Jetson でも他プラットフォームと同程度に「wheel をインストールするだけで import できる」状態にすることを目的とする。

## 優先度根拠

Medium とする。

- Jetson は Sora Python SDK が公式サポートするターゲットの 1 つであり、ユーザー環境での import 失敗は影響が大きい。
- 一方で、JetPack 標準環境では `tegra` / `nvidia` のロケーションが `/etc/ld.so.conf.d/` 経由で動的リンカに登録されているケースもあり、必ず全環境で再現するわけではない。実環境依存で再現する「不安定な ImportError」となるため High ではなく Medium。
- 同種の設定が `raspberry-pi-os` 側には入っており、Jetson だけ抜けている整合性の欠落でもあるため、放置せず修正する。

## 現状

`CMakeLists.txt` の 144-159 行付近:

```cmake
elseif(TARGET_OS STREQUAL "jetson")
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
  target_link_directories(sora_sdk_ext
    PRIVATE
      ${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/tegra
      ${CMAKE_SYSROOT}/usr/lib/aarch64-linux-gnu/nvidia)
```

`target_link_directories` でビルド時のライブラリ検索パスは追加されているが、`sora_sdk_ext` の `BUILD_RPATH` / `INSTALL_RPATH` は未設定。
一方、直後の `raspberry-pi-os` 分岐では:

```cmake
set_target_properties(sora_sdk_ext PROPERTIES BUILD_RPATH "\$ORIGIN")
```

が設定されており、`sora_sdk_ext.so` と同じディレクトリの共有ライブラリを実行時に解決できる。
Jetson 用の Tegra / NVIDIA ライブラリは wheel に同梱されておらず JetPack 標準ロケーションに存在する前提だが、その「前提」がどこにも明文化されていない。
動的リンカが該当ディレクトリを既定で探索するかは JetPack のバージョンとシステム設定に依存し、ユーザー環境次第で `libnvbuf_*.so not found` 系の ImportError が再現する。

## 設計方針

以下のいずれか、または併用で対応する。実装時にどちらが妥当か判定する。

1. Jetson 向け `sora_sdk_ext` ターゲットに `INSTALL_RPATH` / `BUILD_RPATH` を設定する。
   - 例: `/usr/lib/aarch64-linux-gnu/tegra:/usr/lib/aarch64-linux-gnu/nvidia` を `INSTALL_RPATH` として焼き込む。
   - JetPack の標準パスをハードコードするのか、ビルド変数経由で差し替え可能にするかは検討する。
2. wheel をインストールするだけでは Tegra / NVIDIA ライブラリの解決を保証できないことを `README` の Jetson セクションに明文化し、JetPack 標準環境を前提とすることをドキュメントで担保する。
   - この場合でも、せめて `BUILD_RPATH "\$ORIGIN"` 程度は `raspberry-pi-os` と揃えて設定する。
3. リンクディレクトリ追加と RPATH 設定を同じブロックに集約し、`raspberry-pi-os` 側との非対称性を解消する。

`raspberry-pi-os` 側の設定パターン (`BUILD_RPATH "\$ORIGIN"`) を起点に Jetson 向けを揃える形が最小変更となる見込み。

## 完了条件

- Jetson 用 wheel をクリーンな JetPack 環境にインストールし、`LD_LIBRARY_PATH` を手当てせずに `import sora_sdk` が成功すること。
- `CMakeLists.txt` の Jetson 分岐と `raspberry-pi-os` 分岐で RPATH 設定の方針が揃っていること (Jetson だけ抜けていない状態)。
- 上記 2 のドキュメント方針を採るならば、Jetson セクションに動的リンカの前提が明記されていること。
- 既存のビルドが壊れないこと (ubuntu / macOS / Windows のジョブが通る)。
