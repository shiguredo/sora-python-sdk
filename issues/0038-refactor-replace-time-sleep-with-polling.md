# テストの `time.sleep()` をイベント待機・ポーリングに置換して flake を減らす

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-replace-time-sleep-with-polling
- Polished: 2026-07-30

## 目的

テストコードに `time.sleep()` が 85 箇所散在しており、特に「connect → `time.sleep(N)` → stats 取得」が定型化している。固定待機は ARM ランナーや負荷時に flake する温床となるため、条件成立まで polling するパターンへ統一する。

## 優先度根拠

Medium とする。

- CI 安定性に直接影響する。固定 sleep は遅い環境で stats が育ちきらず flake する一方、速い環境でテスト時間を無駄に消費する両側の問題を抱える。
- 件数が多いので一括で潰す必要はあるが、致命バグ修正の優先度よりは低い。
- High ではない理由は、現状で再現が安定して赤い既知バグになっているわけではないため。Broken Windows 的に放置すると flake が日常化し本物の失敗を覆い隠す副作用がある。

## 現状

`tests/` 配下に `time.sleep()` が 85 箇所ある (`rg -n "time\.sleep" tests/ | wc -l`)。主な使用パターン:

- `tests/test_authz.py` の `test_sendonly_authz_video_codec_type` / `test_sendonly_authz_simulcast` 内: `connect → time.sleep(N) → stats 検証`
- `tests/test_messaging.py` の `test_messaging` 内: 接続後 switched 表明前の待機、メッセージ送信後の待機
- `tests/test_simulcast.py` の `test_simulcast` 内: stats 取得前の待機
- `tests/test_signaling_message.py` の `test_signaling_message` 内: シグナリングメッセージ受信待ち
- 他多数

一方、`tests/test_audio_sink_read_gil.py` の `_wait_audio_sink` 関数には正しい polling パターンが存在する:

```python
def _wait_audio_sink(client: SoraClient, timeout_s: float = 30.0):
    """on_track が発火して audio sink が生成されるまでポーリングして待つ"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        audio_sink = client._audio_sink
        if audio_sink is not None:
            return audio_sink
        time.sleep(0.1)
    raise AssertionError("audio sink が生成されなかった")
```

このパターンが他のテストに展開されていない。

## 設計方針

- 共通ヘルパを `tests/client.py` に module-level 関数として追加する (既存の `SoraClient.wait_notify` メソッドと同一ファイルに配置し、`wait_*` プレフィックスで命名を揃える)。例:
  - `wait_until(pred, timeout_s, interval_s=0.1, label="")`: 述語が True を返すまで polling する汎用ヘルパ。タイムアウト時に `label` を含めた AssertionError を raise する。
  - `wait_stats(client, pred, timeout_s, label="")`: stats を取得して `pred(stats)` が True になるまで polling する。
- 待機手段の使い分け: 既存の `time.sleep` の大半は「stats が育つのを待つ」「コールバックが来るのを待つ」であり、スレッド間通知を伴わないため **polling (wait_until / wait_stats) に統一する**。`Event.wait` は `wait_notify` のような既存のイベント駆動パターンに限定し、新規の sleep 置換には使わない。
- 既存の `time.sleep(N)` を以下のいずれかに置換する:
  - 「ある状態に到達したら次へ進む」場合は `wait_until` に置換する。
  - 「ビットレートが立ち上がるまで」など stats の育ちを待つ場合は `wait_stats` に置換する。
- フレーム送出ループ (`_fake_audio_loop` 等) の周期 `time.sleep(0.02)` のような「意図的なリアルタイム周期」は対象外。
- issue 0040 (`wait_notify` のタイムアウト改善) と協調する。0040 が `wait_notify` に `label` パラメータを追加する設計のため、本 issue の `wait_until` / `wait_stats` も `label` パラメータを持ち、命名・シグネチャの整合を保つ。0040 とは独立に実装可能だが、`tests/client.py` の同一ファイルを変更するため、マージ順に注意する。
- 移行は段階的に行ってよい (テストファイル単位で PR を分けるなど)。

## 完了条件

- `rg -n "time\.sleep" tests/` の結果が、対象外パターン (フレーム送出ループの周期 sleep、`wait_until` / `wait_stats` 内部の `time.sleep(0.1)` ポーリング間隔) を除いて 0 件になること。
- 共通の polling ヘルパ (`wait_until`, `wait_stats`) が `tests/client.py` に追加され、複数テストから利用されていること。
- ヘルパにはタイムアウト時にどの条件で待っていたかを assert メッセージに含めること (`label` パラメータ)。
- 既存のテストがすべて pass すること。
- CI の flake 率が悪化しないこと (定性確認でよい)。
