# `tests/test_signaling_notify.py` で `wait_notify` のタイムアウトがデフォルト 5 秒に張り付き flake する問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-wait-notify-timeout-too-short
- Polished: 2026-07-28

## 目的

`tests/test_signaling_notify.py` の最後の `wait_notify` 呼び出しは `c2` の `disconnect` 直後に `c1` 側で `connection.destroyed` の通知を待っているが、`wait_notify` の `timeout` のデフォルト値である 5 秒で待っている。サーバの通知伝搬遅延や CI 環境の負荷次第で 5 秒に間に合わず `queue.Empty` で flake する。

タイムアウトをテスト側で明示し、かつ「タイムアウト時にそれまでに受信した notify の内訳が分かる」assert メッセージにすることで、flake 発生時の原因切り分けを容易にする。

## 優先度根拠

Medium とする。

- 製品コードのバグではないが、`connection.destroyed` の通知遅延は実環境 (チャンネル人数の多いとき) でも発生し得る。テスト側の固定 5 秒では検証不足。
- High ではない理由は、現状で恒常的に赤くなっているわけではない (再実行で通る) ため。
- Low ではない理由は、flake が発生したとき `queue.Empty` だけが報告されて「どの notify が来ていたか」が不明で原因切り分けに時間がかかり、再発防止コストが高い。

## 現状

該当箇所:

```python
# tests/test_signaling_notify.py:37-40
# c1 に c2 の connection.destroyed が通知される
notify = c1.wait_notify(lambda notify: notify["event_type"] == "connection.destroyed")
assert notify["connection_id"] == c2.connection_id
assert notify["channel_connections"] == 1
```

`wait_notify` の定義 (`tests/client.py:510-514`):

```python
def wait_notify(self, pred: Callable[[dict], bool], timeout: int | None = 5):
    while True:
        notify = self._notify_queue.get(block=True, timeout=timeout)
        if pred(notify):
            return notify
```

問題:

1. `timeout` のデフォルトが 5 秒で、テスト側で明示していない。`connection.destroyed` の伝搬は WebSocket 経由のためネットワーク状況によりばらつきがあり、CI 負荷時には 5 秒では不足し得る。
2. `wait_notify` は while ループ内で「述語にマッチしない notify」を捨てているが、タイムアウト時にどの notify を消費したか・残っていたかが分からない。`queue.Empty` だけが起こり、デバッグ情報が乏しい。

## 設計方針

- 変更対象ファイル: `tests/client.py`、`tests/test_signaling_notify.py`
- `tests/test_signaling_notify.py` の各 `wait_notify` 呼び出し (4 箇所: 15, 26, 33, 38 行目) に明示的なタイムアウトを指定する。`connection.destroyed` を待つ箇所は 15 秒、`connection.created` を待つ箇所は 10 秒とする。
- `wait_notify` のシグネチャに「タイムアウト時のエラーメッセージ用ラベル」を追加できるようにする。例:
  ```python
  def wait_notify(self, pred, timeout=5, label: str | None = None):
      ...
      except queue.Empty:
          raise AssertionError(
              f"notify 待機がタイムアウトしました (label={label}, timeout={timeout}s, "
              f"received_event_types={...})"
          )
  ```
- `wait_notify` が捨てた notify の `event_type` をリストで覚えておき、タイムアウト時の assert メッセージに含める。これにより「どこまで受信していたか」が分かる。
- `wait_notify` の呼び出しは現状 `test_signaling_notify.py` の 4 箇所のみであり、全箇所に label を付ける。
- issue 0038 (`refactor-replace-time-sleep-with-polling`) の `wait_*` ヘルパ追加時に label 相当のパラメータを整合させること。0038 とは独立に実装可能。

## 完了条件

- `tests/test_signaling_notify.py` の `wait_notify` 呼び出しすべてに明示的なタイムアウトと用途が分かる label が付くこと。
- `wait_notify` がタイムアウトしたとき、label と、それまでに受信した `event_type` のリストが assert メッセージに含まれること。
- 既存のテストがすべて pass すること。
