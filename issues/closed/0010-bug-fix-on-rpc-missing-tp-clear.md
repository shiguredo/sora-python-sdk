# SoraConnection の on_rpc が tp_clear から漏れて参照循環を回収できない問題を修正する

- Priority: Medium
- Created: 2026-05-29
- Polished: 2026-06-01
- Completed: 2026-06-01
- Model: Opus 4.8
- Branch: feature/fix-on-rpc-missing-tp-clear

## 目的

`SoraConnection` の Python GC 連携で、`connection_tp_traverse` が `on_rpc_` を GC に報告している (`Py_VISIT`) のに、`connection_tp_clear` が `on_rpc_` を解放していない。この traverse/clear の非対称は CPython の循環 GC の契約 (tp_clear は tp_traverse が報告する参照を解放して循環を断ち切れること) に反する。`on_rpc` ハンドラを含む参照循環のうち、接続オブジェクトの `tp_clear` を通してしか断ち切れないものを循環 GC が回収できず、接続オブジェクトのグラフ全体がリークしうる。

本 issue はこの非対称を解消し、`on_rpc_` を他の 10 個のコールバックと同様に `tp_clear` で解放する。

## 優先度根拠

Medium とする。

- 帰結はメモリリークであり、クラッシュや未定義動作ではない。プロセスを巻き込んで落ちることはなく回復可能 (プロセス再起動でリセット)。この点で crash 系の issue (`0008` / `0009`) より致命度は低い。
- traverse が報告する参照を clear が解放しないのは GC 契約違反であり、他の 10 個のコールバックは全て `tp_clear` で解放している。`on_rpc_` だけが例外。
- 実際にリークするのは「接続オブジェクトの `tp_clear` を通してしか断ち切れない参照循環」に限られ (機序は「根本原因」を参照)、発生条件は限定的である。ただし顕在化した場合は接続グラフ全体 (トラック・ソース・native の `SoraConnection` を含む) が回収されず、長時間稼働・多数接続のアプリで累積しうる。
- 修正は他の 10 個のコールバックが既に `tp_clear` で実施している 1 行 (`conn->on_rpc_ = nullptr;`) の追加のみ。実証済みのパターンでリグレッションリスクは低い。

## 現状

### 根本原因

`src/sora_sdk_ext.cpp` の GC スロット実装で、`connection_tp_traverse` と `connection_tp_clear` が扱うコールバックの集合がずれている。

- `connection_tp_traverse` (`src/sora_sdk_ext.cpp:218-281`) は 11 個のコールバックを `Py_VISIT` で GC に報告する。`on_rpc_` も含む (`:260-263`)。
- `connection_tp_clear` (`src/sora_sdk_ext.cpp:283-300`) は 10 個だけ `nullptr` 代入で解放する。`on_rpc_` だけが漏れている。
- `on_rpc` は `.def_rw("on_rpc", &SoraConnection::on_rpc_)` (`src/sora_sdk_ext.cpp:512`) で公開された設定可能な属性で、Python callable を保持する (`on_rpc_` は `std::function<void(nb::bytes)>`、`src/sora_connection.h:153`)。

CPython の循環 GC の契約は次のとおり。

- `tp_traverse` は所有する全ての Python 参照を報告し、GC が参照循環を検出できるようにする。
- `tp_clear` は循環を断ち切るために参照を解放する。tp_traverse が報告する参照は tp_clear で解放できることが期待される。

`on_rpc_` は traverse で報告されるが clear で解放されないため、`on_rpc` ハンドラが接続オブジェクトとの参照循環に含まれ、かつその循環が接続オブジェクトの `tp_clear` を通してしか断ち切れない場合、GC は循環を検出できても断ち切れない。結果として循環に含まれるオブジェクト (接続オブジェクト、ハンドラ、それらが推移的に保持するトラック・ソース・native オブジェクト) がプロセス終了まで回収されない。

### 経緯 (意図的な除外ではない)

`tp_clear` は `ecc4d3a`「tp_clear を入れる」で導入され、その時点では `on_rpc` は未追加で 10 個のコールバックを扱っていた。`on_rpc` を追加した `04636a8`「rpc ラベルに対応する」(2025-05-28) の diff では、同一コミット内で `tp_traverse` への `Py_VISIT` と `def_rw("on_rpc")` は追加されたのに、`connection_tp_clear` への `nullptr` 代入だけが欠落している。git 全履歴を通じて `on_rpc_ = nullptr` が `connection_tp_clear` に現れたことは一度もない。

`on_rpc_` を `tp_clear` から意図的に除外する理由は存在しない。`on_rpc_` は他の 10 個と同種のコールバック (Python callable を保持する `std::function`、`def_rw` で公開。全 11 個が `src/sora_connection.h:144-156` に定義) であり、別扱いする根拠はない。また `on_rpc_` を解放する経路は他に無い (出現箇所は `def_rw`・呼び出し `src/sora_connection.cpp:223`・`tp_traverse` のみで、デストラクタや切断処理での `nullptr` 化も無い)。以上より本件は追加漏れである。

### 利用側で回避できるか

GC 連携 (`tp_traverse` / `tp_clear`) は native 拡張側の責務で、利用側から制御する手段はない。利用側で参照循環を一切作らないよう徹底すれば理屈の上では回避できるが、コールバックに `self` のメソッドやクロージャを渡すのは一般的であり、循環を完全に避けることを利用側に要求するのは非現実的。

## 設計方針

`on_rpc_` を他の 10 個のコールバックと同様に `tp_clear` で解放する。`connection_tp_clear` に 1 行追加する。挿入位置は `tp_traverse` の順序に合わせ `on_message_` と `on_switched_` の間とする。

```cpp
int connection_tp_clear(PyObject* self) {
  if (!nb::inst_ready(self)) {
    return 0;
  }

  SoraConnection* conn = nb::inst_ptr<SoraConnection>(self);
  conn->on_set_offer_ = nullptr;
  conn->on_ws_close_ = nullptr;
  conn->on_disconnect_ = nullptr;
  conn->on_signaling_message_ = nullptr;
  conn->on_notify_ = nullptr;
  conn->on_push_ = nullptr;
  conn->on_message_ = nullptr;
  conn->on_rpc_ = nullptr;  // 追加
  conn->on_switched_ = nullptr;
  conn->on_track_ = nullptr;
  conn->on_data_channel_ = nullptr;
  return 0;
}
```

- Python から見える API・挙動は変わらず、後方互換性に影響はない。
- 本リポジトリ単独で完結する。外部依存の変更は不要。

### テスト方針

基本方針は「コード検査による traverse/clear の対称性確認」を正当性の根拠とする (`0009` と同様)。`connection_tp_traverse` が `Py_VISIT` するコールバック集合と `connection_tp_clear` が `nullptr` 代入するコールバック集合が完全に一致することを確認する。

リグレッションテストは作成しない。実現可能性を調査した結果、堅牢なテストの作成コストが見合わないと判断したため。根拠は以下。

- 接続オブジェクトの生成自体はサーバ無しで可能。`Sora::CreateConnection` (`src/sora.cpp`) は `conn->Init(config)` 経由で `sora::SoraSignaling::Create` までは実行するが、実際のネットワーク接続は `Connect()` で初めて行われる。ダミーの `signaling_urls` / `role` / `channel_id` を渡して `create_connection` するだけならサーバ実体は不要 (モック・スタブも不要)。
- 本質的な難所は「参照循環を、接続オブジェクトの `tp_clear` を通してしか断ち切れない形に組む」必要がある点。CPython の循環 GC は到達不能な循環の clear 可能な全メンバに `tp_clear` を呼ぶため、循環内に接続オブジェクト以外で clear 可能なオブジェクトが 1 つでもあると、そこで循環が断たれて修正前でも回収され差が出ない (偽陰性)。Python 3.13.7 で実測したところ、通常の `__dict__` / `__slots__` インスタンス・クロージャ・tuple 経由のいずれの循環も全て回収された。
- 差を観測するには接続オブジェクト以外の全参加者を clear 不可にする必要があり、`conn.on_rpc = (conn,).count` のような CPython 内部仕様 (tuple やビルトインメソッドが `tp_clear` を持たないこと) に依存する技巧的な作りになる。`on_rpc` の本来の型 (`Callable[[bytes], None]`) を逸脱するハックを含み保守性が低いため採用しない。

## 完了条件

- `connection_tp_clear` が `on_rpc_` を解放していること (`tp_traverse` と `tp_clear` が扱うコールバックの集合が一致すること)
- ビルドが通り、既存テストが全て通ること
- `CHANGES.md` の `## develop` に `[FIX]` エントリを担当者行付きで追記していること (CLAUDE.md の種別順・書式に従う)

## 解決方法

`src/sora_sdk_ext.cpp` の `connection_tp_clear` に `conn->on_rpc_ = nullptr;` を 1 行追加し、`on_message_` と `on_switched_` の間に挿入した。これにより `connection_tp_traverse` が `Py_VISIT` するコールバック集合と `connection_tp_clear` が `nullptr` 代入するコールバック集合が完全に一致し、traverse/clear の対称性が回復した。

`CHANGES.md` の `## develop` に `[FIX]` エントリを担当者行付きで追記した。
