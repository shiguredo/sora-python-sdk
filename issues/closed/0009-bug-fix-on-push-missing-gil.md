# SoraConnection::OnPush の GIL 未取得による Python インタプリタ破壊を修正する

- Priority: High
- Created: 2026-05-29
- Polished: 2026-05-29
- Completed: 2026-06-01
- Model: Opus 4.8
- Branch: feature/fix-on-push-missing-gil

## 目的

Sora サーバからの `push` シグナリングメッセージ受信時に呼ばれる `on_push` コールバックが、GIL (Python のグローバルインタプリタロック) を取得しないまま Python 関数を呼び出している。これは Python C API の利用規約違反 (未定義動作) であり、CPython のインタプリタ状態の整合性を壊す。これによりプロセス全体が SIGSEGV でクラッシュしうる。native レイヤのクラッシュは Python 例外として捕捉できず、利用側アプリケーションを巻き込んでプロセスごと停止させる。

本 issue はこの未定義動作を解消し、`on_push` を他のコールバックと同じ GIL 取得規約に揃える。

## 優先度根拠

High とする。

- `on_push` ハンドラを設定し、サーバが `push` を送る構成では、ハンドラが呼ばれる全 push で GIL 非保持の Python C API 呼び出し (未定義動作) が確定的に発生する。クラッシュとして顕在化するかはタイミング依存で確率的である。
- High と判断する主因は、native レイヤのクラッシュであり Python 側に回避手段がないこと (後述「利用側で回避できるか」)。
- 唯一の減点要素は「`push` 機能を使うアプリに限られる」点だが、push を使うアプリにとっては「いずれ必ず壊れる」状況であり、致命度を下げる根拠にはならない。
- 修正は Python を呼ぶ他の 10 個のコールバックが既に実施している 1 行 (`gil_scoped_acquire acq;`) の追加のみ。実証済みのパターンでリグレッションリスクは低い。

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

- `on_push_` は `std::function<void(std::string)>` (`src/sora_connection.h:151`) で、Python 側で `connection.on_push = ...` と設定された Python callable を保持する (`src/sora_sdk_ext.cpp` の `.def_rw("on_push", &SoraConnection::on_push_)`)。これを呼ぶと Python C API に降りる。
- `call_python` (`src/sora_call.h`) は呼び出しを try/catch で包むだけで GIL は取得しない。GIL の取得は呼び出し側の責務。
- Python を呼ぶ他の 10 個のコールバック (`OnSetOffer` / `OnDisconnect` / `OnNotify` / `OnMessage` / `OnRpc` / `OnSwitched` / `OnSignalingMessage` / `OnWsClose` / `OnTrack` / `OnDataChannel`) は全て先頭で `gil_scoped_acquire acq;` を呼ぶ。Python を呼ばない `OnRemoveTrack` ですら防御的に取得している。Python を呼ぶコールバックのうち、GIL を取得しないのは `OnPush` が唯一。

`OnPush` は GIL を保持していない SDK 内部スレッド (libwebrtc の signaling / worker スレッドや Boost.Asio の io_context スレッドなど) から呼ばれる。具体的にどのスレッドかは依存ライブラリ側の実装に属し本リポジトリのコードからは断定できないが、「GIL 非保持の内部スレッドから呼ばれる」という点は本リポジトリ内の次の事実が裏付ける。

1. `OnPush` は `OnNotify` / `OnMessage` 等と同じ `SoraSignalingObserver` の virtual override 経由で、それらと同一のシグナリングディスパッチ層から呼ばれる (`src/sora_connection.h` の `SoraSignalingObserver`)。兄弟コールバックと構造的に同一の経路であり、それらが内部スレッドから呼ばれる以上 `OnPush` も同じ内部スレッドから呼ばれる。
2. Python を呼ぶ他の全コールバックが先頭で GIL を取得していること自体が、これらがメインの GIL 保持スレッド以外から呼ばれるとメンテナが判断している証左である。
3. `Disconnect` が `OnDisconnect` の到来を別スレッド前提で待つために GIL を解放する設計になっている (`src/sora_connection.cpp:79-83` の `GILLock`)。

GIL を取得せずに Python C API を呼ぶと、`on_push_` (= Python callable) に対する参照カウント操作などが、GIL を保持して Python を実行している別スレッドと競合する。CPython では参照カウントも GC も GIL 保持下で動くため、競合相手は GC に限らずメインスレッドの Python 実行全般であり、非アトミックな参照カウント操作が衝突すると解放済みオブジェクト参照やヒープ破壊といった形でメモリ安全性が壊れうる。破壊は `on_push` ハンドラ内に留まらず、後続のメインスレッド上の任意の Python 処理 (無関係なコード) で SIGSEGV として顕在化しうる。

### 経緯 (意図的な省略ではない)

git 全履歴を通じて `OnPush` は一度も GIL を取得していない。コールバックへ GIL 取得を導入したコミット `2fd085b`「別スレッドからのコールバックでは最初に GIL を獲得する」で、当時存在したコールバックに `gil_scoped_acquire` が一斉導入されたが `OnPush` だけ漏れた。その後に追加されたコールバック (`OnRpc` 等) は最初から GIL 取得済みで実装された。結果として現行 `develop` では、Python を呼ぶコールバックのうち `OnPush` だけが規約から漏れたまま残っている。`OnPush` を特別扱いする設計上の理由は存在せず、本件は規約の適用漏れである。

### 利用側で回避できるか

回避できない。`on_push` を呼ぶスレッドや GIL の保持は SDK 内部の責務で、利用側から制御する API はない。利用側は `connection.on_push = handler` を設定するだけで、ハンドラがどのスレッド・GIL 状態で呼ばれるかには関与できない。

## 設計方針

`OnPush` を他のコールバックと完全に同じ規約に揃える。関数先頭 (`if` の外) に `gil_scoped_acquire acq;` を 1 行追加する。

```cpp
void SoraConnection::OnPush(std::string text) {
  gil_scoped_acquire acq;
  if (on_push_) {
    call_python(on_push_, text);
  }
}
```

- `gil_scoped_acquire` (`src/gil.h`) は `PyGILState_Ensure()` を RAII で包んだもので、任意の C スレッドから安全に GIL を取得し、関数を抜ける際 (例外送出時を含む) に解放する。他のコールバックが使っているものと同一。
- Python から見える API・シグネチャ・挙動は変わらず、後方互換性に影響はない。
- 本リポジトリ単独で完結する。外部依存の変更は不要。

### テスト方針

性質の異なる 2 種類を区別する。

1. クラッシュを確定的に再現するテスト: 追加できない。クラッシュの顕在化には push 受信とメインスレッドの Python 実行のタイミング一致、および確率的なメモリレイアウトの一致が必要で、再現率は極めて低い。
2. `OnPush` の経路を機能的に通すテスト: 現状 `tests/` には `on_push` を設定するテストが無い (`tests/client.py` は他のコールバックを配線するが `on_push` は未配線)。`client.py` で `on_push` を配線し、接続後に push を受信させる構成は、ハーネスの形 (接続 → 管理 API でサーバ側アクションを発火 → コールバックを検証) としては `tests/test_key_frame_request.py` 等と同型である。ただし (a) push を発火させる管理 API は現状 `tests/api.py` に無く (あるのは GetStats / Disconnect / RequestKeyFrame のみ)、テスト環境の Sora が push を発火できるか自体も本リポジトリからは確認できない、(b) 仮に書けても本バグは確率的クラッシュであり、push 受信が成功するだけの機能テストは未修正版でも通常 pass するため、クラッシュを捕捉するゲートにはならない (経路カバレッジが増えるのみ)。

以上より、本修正の正当性は「コード検査による根本原因の確定」と「GIL 取得規約 (Python を呼ぶ他 10 コールバックとの一致)」に置く。機能テスト (2) の追加は push 発火手段が用意できる場合の経路カバレッジ向上として任意であり、必須の完了条件には含めない。

## 完了条件

- `SoraConnection::OnPush` が他のコールバックと同様に関数先頭で `gil_scoped_acquire acq;` を取得していること
- ビルドが通り、既存テストが全て通ること。ただし `on_push` を設定するテストは存在しないため、これは `OnPush` の経路を検証するものではなく、ビルドが通り他機能にリグレッションが無いことの確認である
- `CHANGES.md` の `## develop` に `[FIX]` エントリを担当者行付きで追記していること (CLAUDE.md の種別順・書式に従う)

## 解決方法

`src/sora_connection.cpp` の `SoraConnection::OnPush` の関数先頭 (`if` の外) に `gil_scoped_acquire acq;` を 1 行追加し、Python を呼ぶ他のコールバックと同じ GIL 取得規約に揃えた。

```cpp
void SoraConnection::OnPush(std::string text) {
  gil_scoped_acquire acq;
  if (on_push_) {
    call_python(on_push_, text);
  }
}
```

あわせて `CHANGES.md` の `## develop` に `[FIX]` エントリを追記した。
