# テストの `time.sleep()` をイベント待機・ポーリングに置換して flake を減らす

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-replace-time-sleep-with-polling

## 目的

テストコードに `time.sleep()` が 70 箇所以上散在しており、特に「connect → `time.sleep(N)` → stats 取得」が定型化している。固定待機は ARM ランナーや負荷時に flake する温床となるため、`Event.wait(timeout)` または条件成立まで polling するパターンへ統一する。

## 優先度根拠

Medium とする。

- CI 安定性に直接影響する。固定 sleep は遅い環境で stats が育ちきらず flake する一方、速い環境でテスト時間を無駄に消費する両側の問題を抱える。
- 件数が多いので一括で潰す必要はあるが、致命バグ修正の優先度よりは低い。
- High ではない理由は、現状で再現が安定して赤い既知バグになっているわけではないため。Broken Windows 的に放置すると flake が日常化し本物の失敗を覆い隠す副作用がある。

## 現状

`tests/` 配下に `time.sleep()` が 70 箇所以上ある (`rg -n "time\.sleep" tests/ | wc -l` の概算)。主な使用パターン:

- `tests/test_authz.py:26, 70`: `connect → time.sleep(N) → stats 検証`
- `tests/test_messaging.py:24-31`: メッセージ送受信タイミングの調整
- `tests/test_simulcast.py:74`: stats 取得前の待機
- `tests/test_signaling_message.py:15`: シグナリングメッセージ受信待ち
- 他多数

これらは「事象が起きるまで」ではなく「N 秒経つまで」待つため、N が短いと flake し、N が長いと CI 時間が浪費される。

一方、`tests/test_audio_sink_read_gil.py` には正しい polling パターンが存在する:

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

- 共通ヘルパを `tests/client.py` または専用モジュールに追加する。例:
  - `wait_until(pred, timeout_s, interval_s=0.1)`: 述語が True を返すまで polling する汎用ヘルパ。
  - `wait_stats(client, pred, timeout_s)`: stats を取得して `pred(stats)` が True になるまで polling する。
- 既存の `time.sleep(N)` を以下のいずれかに置換する:
  - 「ある状態に到達したら次へ進む」場合は polling helper か `Event.wait(timeout)` に置換する。
  - 「ビットレートが立ち上がるまで」など stats の育ちを待つ場合は「条件を満たすまで polling (最大 N 秒)」に置換する。
- 既存の `wait_notify` (`tests/client.py:510`) と整合させ、API 命名を揃える (`wait_*` プレフィックス)。
- フレーム送出ループ (`_fake_audio_loop` 等) の周期 `time.sleep(0.02)` のような「意図的なリアルタイム周期」は対象外。
- 移行は段階的に行ってよい (テストファイル単位で PR を分けるなど)。

## 完了条件

- `rg -n "time\.sleep" tests/` の結果が大幅に減ること (周期送出ループや明確な遅延テスト目的を除き、原則撲滅)。
- 共通の polling helper が `tests/client.py` 等に追加され、複数テストから利用されていること。
- helper にはタイムアウト時にどの条件で待っていたかを assert メッセージに含めること。
- 既存のテストがすべて pass すること。
- CI の flake 率が悪化しないこと (定性確認でよい)。
