# テストのログメッセージを日本語に統一する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-test-logs-to-japanese

## 目的

AGENTS.md の規約「テストのログメッセージは全て日本語にすること」に違反している箇所が広範囲に残っており、これを解消する。

`tests/` 配下の `print` の大半が英語のまま放置されており、テスト失敗時の出力が英語と日本語が混在している。規約に合わせて統一することで、テスト失敗時の状況把握を日本語話者の開発者がスムーズに行えるようにし、また「規約があるが守られていない」状態を解消する。

## 優先度根拠

Medium とする。

- 機能には影響しない純粋なリファクタであり緊急度は無い。ただし「規約があるが守られていない」状態は他の規約違反の温床になりやすく、Broken Windows として早めに直すべき位置付け。
- 件数が広範囲 (`tests/client.py` だけで 10 数箇所、各テストファイルにも散在) に及ぶため、放置するほど作業量が増える。
- High ではない理由は、テスト挙動・CI 結果には影響しないため。

## 現状

AGENTS.md L13 に「テストのログメッセージは全て日本語にすること」と明記されているが、以下の箇所が英語のまま残っている (主要なもの)。

- `tests/client.py`
  - L234, L236: `"__exit__: disconnecting"` / `"__exit__: disconnected"`
  - L261, L263: `"disconnect: disconnecting"` / `"disconnect: disconnected"`
  - L267: `"send: label=..."`
  - L425: `f"type: close: {message}"`
  - L448: `"Switched to DataChannel Signaling: ..."`
  - L461-462: `"Connected Sora: channel_id=..."`
  - L466: `"Received message: label=..."`
  - L470: `"DataChannel opened: label=..."`
  - L475: `"Disconnected Sora: error_code=..."`
  - L493: `"WebSocket closed: code=..."`
- `tests/test_encoded_transform.py`
  - L150, L159, L163, L292, L301, L305 などの `print` メッセージ
- `tests/test_vad.py`
  - L91, L100, L104, L112 などの `print` メッセージ
- `tests/test_amd_amf.py`
  - L108-110 の `print` メッセージ
- 他、`tests/` 配下のほぼ全ファイルに英語の `print` が残存

なお WebRTC stats のキー名 (`bytesSent`、`framesEncoded`、`qualityLimitationReason` 等) は API 仕様で定義された識別子であり、ログ中に出現してもキー名自体は日本語化しない。

## 設計方針

- `tests/` 配下の `print`・log・assert メッセージで「人間向けの説明文」を日本語化する。
- 仕様で定義された英単語 (stats のキー名、`event_type` の値、HTTP ヘッダ名など) はそのまま残す。
- 変数の `f-string` 中の英語部分も日本語に書き換える。例: `print(f"send: label={label}, data={data!r}")` → `print(f"送信: label={label}, data={data!r}")`。
- 全角・半角間スペースの規約 (AGENTS.md L9) を満たすこと。
- 既存のテストが落ちないことを確認 (メッセージ文字列に対する assert が無いことを grep で確認する)。
- 1 ファイル単位でコミットを分けるか否かは `shiguredo-git` スキルの粒度に従う。

## 完了条件

- `rg -n "print\(" tests/` の結果から「英文のみで構成された人間向けメッセージ」が検出されないこと (stats キー名や `event_type` 値など仕様由来の識別子のみで構成された f-string は除く)。
- `tests/` 配下の `print` / log / assert メッセージで人間向けに書かれた英文が残らないこと。
- 既存のテストがすべて pass すること。
- メッセージ文字列に依存した assert (もしあれば) が壊れていないこと。
