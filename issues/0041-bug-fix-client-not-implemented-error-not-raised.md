# `tests/client.py` の `_on_signaling_message` で `NotImplementedError` を raise せずに silent 通過している問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-client-not-implemented-error-not-raised

## 目的

`tests/client.py:429-430` の `case _:` 分岐で `NotImplementedError(...)` を **生成しているだけで `raise` していない**。未知のシグナリングメッセージが silent に通過してしまい、テストが「知らないメッセージ種別」を見逃す。

実装意図は明らかに「未知メッセージで失敗する」ことなので、`raise NotImplementedError(...)` に修正する。

## 優先度根拠

Medium とする。

- 製品コードではなくテストヘルパだが、シグナリングプロトコルの安全網として「未知メッセージを検出する」目的の分岐が機能していない。新しいメッセージ種別が増えたとき、テストヘルパが silent に通過するため検知漏れが発生する。
- High ではない理由は、現状で既知のテストを赤くしているわけではない (`type` が既知の値ばかり来ているため case `_:` に落ちていない)。
- Low ではない理由は、明確なコードバグであり、見つけたら直すべきもの。1 行修正で済む。

## 現状

該当箇所 (`tests/client.py:421-430`):

```python
case "disconnect":
    assert signaling_direction == SoraSignalingDirection.SENT
    self._disconnect_message = message
case "close":
    print(f"type: close: {message}")
    assert signaling_type == SoraSignalingType.DATACHANNEL
    assert signaling_direction == SoraSignalingDirection.RECEIVED
    self._close_message = message
case _:
    NotImplementedError(f"Unknown signaling message type: {message['type']}")
```

`case _:` の中で `NotImplementedError(...)` を呼び出しているが、これは「`NotImplementedError` インスタンスを作って捨てている」だけで、例外として raise されない。Python の構文上は完全に有効で、エラーも警告も出ない。結果として、未知の `type` が来ても何事もなくテストが続行される。

`_on_signaling_message` は SDK の `on_signaling_message` コールバックから呼ばれているため、未知メッセージは現状 silent に捨てられる。

## 設計方針

- `NotImplementedError(...)` を `raise NotImplementedError(...)` に修正する。
- エラーメッセージは現状の `f"Unknown signaling message type: {message['type']}"` を残しつつ、規約 (AGENTS.md L13「テストのログメッセージは全て日本語にすること」) を考慮するか検討する。
  - assert 失敗時に出る exception message は「ログメッセージ」というよりも「テストの assert メッセージ」に近いが、テスト側で出るユーザ向け文字列という意味で日本語化が望ましい。例: `f"未知のシグナリングメッセージ種別: {message['type']}"`。
  - 本 issue の主目的は「raise が抜けている」点の修正なので、文字列の日本語化は同時に行うか別 issue とするかは実装時に判断する。
- 同じパターン (`NotImplementedError(...)` を raise せず呼んでいる箇所) が他に無いか `rg -n "NotImplementedError\(" tests/ src/` で確認する。
- 修正後、敢えて未知 type を流すテストは不要 (SDK 経由でしか来ないため)。レビューで読み取れるだけで十分。

## 完了条件

- `tests/client.py:429-430` の `NotImplementedError(...)` が `raise NotImplementedError(...)` に修正されていること。
- `rg -n "(?<!raise )NotImplementedError\(" tests/ src/` で同種のミスが他に検出されないこと (擬似コードなので grep 表現は適宜)。
- 既存のテストがすべて pass すること。
