# src/sora.cpp が BOOST_PP_STRINGIZE の include を欠き Sora C++ SDK 更新でビルドが壊れる問題を修正する

- Priority: High
- Created: 2026-06-01
- Completed: 2026-06-01
- Model: Opus 4.8
- Branch: feature/fix-boost-pp-stringize-missing-include

## 目的

Sora C++ SDK を `2026.2.0-canary.13` に上げた CI ビルド (build_pyi 3.12 / 3.13 / 3.14) が `src/sora.cpp` のコンパイルで失敗する。原因は `src/sora.cpp` が `BOOST_PP_STRINGIZE` を使いながら `<boost/preprocessor/stringize.hpp>` を直接 include しておらず、これまで Sora C++ SDK のヘッダ経由で推移的に取り込まれていたマクロ定義が canary.13 で取り込まれなくなったこと。推移 include への依存を解消し、ビルドを復旧する。

## 優先度根拠

High とする。

- develop ブランチの CI を全面的にブロックしており、リリースに進めない。
- 影響は全 Python バージョン (3.12 / 3.13 / 3.14) のビルドジョブに及ぶ。
- 修正自体は include 1 行の追加で済み、リグレッションリスクは低い。

## 現状

### 症状

CI 実行 (run 26733872285, attempt 3) の build_pyi 3.12 / 3.13 / 3.14 が全て同じエラーで失敗する。

```
src/sora.cpp:216:40: error: expected ')'
src/sora.cpp:223:25: error: expected ';' after expression
src/sora.cpp:223:45: error: invalid suffix '.0.dev7' on floating constant
3 errors generated.
```

### 根本原因

`src/sora.cpp:216` および `:223` で `BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION)` を使用している。

```cpp
config.user_agent = std::optional<std::string>(
    "Mozilla 5.0 (Sora Unity SDK/" BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION) ")");
...
config.sora_client =
    "Sora Python SDK " BOOST_PP_STRINGIZE(SORA_PYTHON_SDK_VERSION);
```

`src/sora.cpp` の include は `sora.h` と `rtc_base/crypto_random.h` のみで、`<boost/preprocessor/stringize.hpp>` を直接 include していない。これまで `BOOST_PP_STRINGIZE` は Sora C++ SDK 側のヘッダ経由で推移的に取り込まれていた。`2026.2.0-canary.13` でその推移 include が無くなったため `BOOST_PP_STRINGIZE` が未定義となり、マクロが展開されず関数呼び出しの形のまま残る。結果 `SORA_PYTHON_SDK_VERSION` (= VERSION ファイルの `2026.1.0.dev7`) がそのまま展開され、`.0.dev7` が浮動小数点リテラルの不正なサフィックスとして弾かれている。

当 SDK 側のコードも VERSION も変えていないため、変化したのは Sora C++ SDK のヘッダ構成のみ。本件は「推移 include に依存していた潜在的な脆さ」が canary.13 で顕在化したものであり、canary.13 自体の不具合ではない。

### canary.11 -> canary.13 で推移 include が無くなった具体的な箇所

Sora C++ SDK のコミット `9867f49e`「deadline_timer の代わりに steady_timer を利用する」が原因。canary.11 -> canary.13 の差分で、以下 3 ヘッダの Boost.Asio タイマー型が `deadline_timer` から `steady_timer` へ置き換えられ、同時に include も `<boost/asio/deadline_timer.hpp>` から `<boost/asio/steady_timer.hpp>` へ変わった。

- `include/sora/data_channel.h`
- `include/sora/sora_signaling.h`
- `include/sora/websocket.h`

これら 3 ヘッダはいずれも当 SDK の `src/sora_connection.h` -> `src/sora.h` 経由で `src/sora.cpp` に取り込まれる。

推移 include の機序は以下。

- `<boost/asio/deadline_timer.hpp>` は `<boost/date_time/posix_time/posix_time_types.hpp>` を include する。Boost.DateTime は内部で `boost/lexical_cast` 等を経由して `boost/preprocessor/stringize.hpp` を取り込む。このため canary.11 までは `BOOST_PP_STRINGIZE` が `src/sora.cpp` で定義済みになっていた。
- `<boost/asio/steady_timer.hpp>` は `<boost/asio/detail/chrono.hpp>` (std::chrono ベース) を使い、Boost.DateTime も Boost.Preprocessor も取り込まない。このため canary.13 で `BOOST_PP_STRINGIZE` が未定義になった。

つまり当 SDK は `BOOST_PP_STRINGIZE` の定義を「Sora C++ SDK が Boost.DateTime を間接 include していること」に暗黙依存していた。canary.13 でその間接経路が消えたため顕在化した。

## 設計方針

`src/sora.cpp` に `#include <boost/preprocessor/stringize.hpp>` を明示的に追加する。推移 include に頼らず、利用するマクロの定義元を直接 include する。

## 完了条件

- `src/sora.cpp` が `<boost/preprocessor/stringize.hpp>` を直接 include していること
- build_pyi (3.12 / 3.13 / 3.14) を含む CI が通ること
- canary.11 -> canary.13 で推移 include が外れた具体的な箇所を「現状」に記録すること

## 解決方法

`src/sora.cpp` に `#include <boost/preprocessor/stringize.hpp>` を明示的に追加した。`// Boost` グループとして標準ヘッダと `// WebRTC` グループの間に配置した。これにより `BOOST_PP_STRINGIZE` の定義を Sora C++ SDK の推移 include に依存せず、利用するマクロの定義元を直接 include する形に改めた。

`CHANGES.md` への追記は不要と判断した。Sora C++ SDK のバージョン更新 (`2026.2.0-canary.13`) 対応の一環としてビルドを通すための変更であり、独立した変更履歴として残す必要がないため。
