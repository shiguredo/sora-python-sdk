# SoraConnection::OnPush の GIL 未取得による Python インタプリタ破壊を修正する

- Priority: High
- Created: 2026-05-29
- Model: Opus 4.8
- Branch: feature/fix-on-push-missing-gil

## 目的

Sora サーバからの `push` シグナリングメッセージ受信時に呼ばれる `on_push` コールバックが、GIL (Python のグローバルインタプリタロック) を取得しないまま Python 関数を呼び出している。これは Python C API の利用規約違反 (未定義動作) で、CPython のインタプリタ状態を破壊する。結果として `on_push` とは無関係なメインスレッド上の Python コードを含め、プロセス全体が SIGSEGV でクラッシュしうる。本 issue はこの未定義動作を解消し、`on_push` を他のコールバックと同じ GIL 取得規約に揃える。

native レイヤのクラッシュ (SIGSEGV) は Python 例外として捕捉できず、利用側アプリケーションを巻き込んでプロセスごと停止させる。

## 優先度根拠

High とする。

- `on_push` を設定し、かつ `push` を送るサーバ構成の場合、push を 1 件受信するたびに GIL 非保持で Python C API を呼ぶ未定義動作が「確定的に」実行される。クラッシュの顕在化はタイミング依存で確率的だが、未定義動作自体は全 push 呼び出しで発生する。
- 帰結はプロセスごとのクラッシュ (SIGSEGV)、もしくはインタプリタ状態の静かな破壊であり、Python 側に回避手段がない。
- 修正は他の 10 個のコールバックが既に実施している 1 行 (`gil_scoped_acquire acq;`) を追加するだけで、誤りようがなくリグレッションリスクはほぼゼロ。
- High にしない論拠は「`push` 機能を使うアプリに限られる」点のみだが、push を使うアプリにとっては「いずれ必ず壊れる」状況であり、致命度を下げる根拠にはならない。本リポジトリの先例 (`0008` のプロセスクラッシュ + 回避不能 = High) と同じ基準で High とする。

## 現状

### 根本原因

`src/sora_connection.cpp` の `SoraConnection::OnPush` だけが GIL を取得せずに Python コールバックを呼んでいる。

```cpp
// src/sora_connection.cpp:208-212 (現状)
void SoraConnection::OnPush(std::string text) {
  if (on_push_) {
    call_python(on_push_, text);
  }
}
```

- `on_push_` は `std::function<void(std::string)>` で、Python 側で `connection.on_push = ...` と設定された Python callable を保持する (`src/sora_sdk_ext.cpp` の `.def_rw("on_push", &SoraConnection::on_push_)`)。これを呼ぶと Python C API に降りる。
- `call_python` (`src/sora_call.h`) は呼び出しを try/catch で包むだけで GIL は取得しない。GIL の取得は呼び出し側の責務。
- 他の Python を呼ぶコールバック (`OnSetOffer` / `OnDisconnect` / `OnNotify` / `OnMessage` / `OnRpc` / `OnSwitched` / `OnSignalingMessage` / `OnWsClose` / `OnTrack` / `OnDataChannel`) は全て先頭で `gil_scoped_acquire acq;` を呼ぶ。Python を呼ばない `OnRemoveTrack` ですら防御的に取得している。`OnPush` がこれらの中で唯一の例外。

`OnPush` は Sora C++ SDK / libdatachannel の内部スレッド (signaling / worker / Boost.Asio の io_context スレッド) から呼ばれる。これらは Python の GIL を保持していない。GIL を取得せずに Python C API を呼ぶと、参照カウント操作やインタプリタ状態 (型キャッシュ等) が他スレッドの Python 実行と競合し、解放済みオブジェクト参照やヒープ破壊 (use-after-free) を引き起こす。破壊は `on_push` ハンドラ内に留まらず、後続のメインスレッド上の任意の Python 処理 (無関係なコード) で SIGSEGV として顕在化しうる。

### 経緯 (意図的な省略ではない)

git 履歴上、`OnPush` は当初から GIL を取得していない。コールバックへ GIL 取得を導入したコミット `2fd085b`「別スレッドからのコールバックでは最初に GIL を獲得する」で他の全コールバックに `gil_scoped_acquire` が追加されたが、`OnPush` だけ漏れている。すなわち本件はメンテナ自身が定めた規約「別スレッドからのコールバックでは最初に GIL を獲得する」の適用漏れであり、`OnPush` を特別扱いする設計上の理由は存在しない。

### 利用側で回避できるか

回避できない。`on_push` を呼ぶスレッドや GIL の保持は SDK 内部の責務で、利用側から制御する API はない。利用側は `connection.on_push = handler` を設定するだけで、ハンドラがどのスレッド・GIL 状態で呼ばれるかには関与できない。

### 環境

- 本リポジトリの現行 `develop` で未修正。上記の GIL 導入コミット `2fd085b` 以降ずっと存在する。
- C 拡張 (`sora_sdk_ext`) のクラッシュは Python の `try/except` で捕捉できず、プロセス全体が落ちる。

## 設計方針

`OnPush` を他のコールバックと完全に同じ規約に揃える。先頭に `gil_scoped_acquire acq;` を 1 行追加する。

```cpp
void SoraConnection::OnPush(std::string text) {
  gil_scoped_acquire acq;
  if (on_push_) {
    call_python(on_push_, text);
  }
}
```

- `gil_scoped_acquire` (`src/gil.h`) は `PyGILState_Ensure()` を RAII で包んだもので、任意の C スレッドから安全に GIL を取得する。他のコールバックが使っているものと同一。
- 本リポジトリ単独で完結する。外部依存の変更は不要。

### 再現テストについて

確定的な再現テストの追加は本質的に困難。クラッシュの顕在化には (1) サーバが `push` を送る構成、(2) 受信と同時にメインスレッドが Python ヒープを操作するタイミング、(3) 確率的なメモリレイアウトの一致、が必要で再現率は極めて低い。したがって本修正の正当性は「コード検査による根本原因の確定」と「GIL 取得規約 (他 10 コールバックとの一致)」に置く。

実 Sora サーバ (モック・スタブ禁止のため必須) に対し `on_push` を設定して push を受信させ、メインスレッドで Python オブジェクトの生成・型チェックを高頻度に行って race window を増幅する負荷テストを `tests/` に追加して修正前後の挙動差を観測する余地はある。ただし確率的でリグレッションゲートとしては弱いため、必須の完了条件には含めない。

## 完了条件

- `SoraConnection::OnPush` が他のコールバックと同様に先頭で `gil_scoped_acquire acq;` を取得していること
- 既存テストが全て通ること
- `CHANGES.md` に `[FIX]` として記載していること

## 解決方法

未着手。
