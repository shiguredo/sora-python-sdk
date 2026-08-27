# テストのログメッセージを日本語に統一する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-test-logs-to-japanese
- Polished: 2026-07-30

## 目的

AGENTS.md の規約「テストのログメッセージは全て日本語にすること」に違反している箇所が広範囲に残っており、これを解消する。

`tests/` 配下の `print` の大半が英語のまま放置されており、テスト失敗時の出力が英語と日本語が混在している。規約に合わせて統一することで、テスト失敗時の状況把握を日本語話者の開発者がスムーズに行えるようにし、また「規約があるが守られていない」状態を解消する。

## 優先度根拠

Medium とする。

- 機能には影響しない純粋なリファクタであり緊急度は無い。ただし「規約があるが守られていない」状態は他の規約違反の温床になりやすく、Broken Windows として早めに直すべき位置付け。
- 件数が広範囲に及ぶため、放置するほど作業量が増える。
- High ではない理由は、テスト挙動・CI 結果には影響しないため。

## 現状

AGENTS.md に「テストのログメッセージは全て日本語にすること」と明記されているが、`tests/` 配下のほぼ全ファイルに英語の `print` が残存している。対象ファイルの全容は `rg -n "print\(" tests/` で確認できる (2026-07-30 時点で 18 ファイル・約 70 箇所)。

主要な英語メッセージの例をシンボル名で示す:

- `tests/client.py`
  - `SoraClient.__exit__` 内: `"__exit__: disconnecting"` / `"__exit__: disconnected"`
  - `SoraClient.disconnect` 内: `"disconnect: disconnecting"` / `"disconnect: disconnected"`
  - `SoraClient.send` 内: `"send: label=..."`
  - `SoraClient._on_signaling_message` の close 分岐内: `"type: close: ..."`
  - `SoraClient._on_switched` 内: `"Switched to DataChannel Signaling: ..."`
  - `SoraClient._on_connect` 内: `"Connected Sora: channel_id=..."`
  - `SoraClient._on_message` 内: `"Received message: label=..."`
  - `SoraClient._on_data_channel` 内: `"DataChannel opened: label=..."`
  - `SoraClient._on_disconnect` 内: `"Disconnected Sora: error_code=..."`
  - `SoraClient._on_ws_close` 内: `"WebSocket closed: code=..."`
  - `SoraClient.connect` 内の assert: `"Could not connect to Sora."`
- `tests/test_encoded_transform.py`
  - `SendonlyEncodedTransform._on_set_offer` / `_on_notify` / `_on_disconnect` 内の print
  - `RecvonlyEncodedTransform._on_set_offer` / `_on_notify` / `_on_disconnect` 内の print
- `tests/test_vad.py`
  - `VAD._on_set_offer` / `_on_notify` / `_on_disconnect` / `_on_frame` 内の print
- 他、`tests/test_amd_amf.py`, `tests/test_nvidia_video_codec.py`, `tests/test_intel_vpl.py`, `tests/test_key_frame_request.py`, `tests/test_degradation_preference.py`, `tests/test_openh264_simulcast.py`, `tests/test_sendonly_recvonly.py`, `tests/test_apple_video_toolbox.py`, `tests/test_audio_sink_read_gil.py`, `tests/test_messaging_header.py`, `tests/test_messaging.py`, `tests/test_version.py`, `tests/test_raspberry_pi.py`, `tests/test_authz_simulcast.py`, `tests/test_simulcast.py` にも英語 print が残存

なお WebRTC stats のキー名 (`bytesSent`、`framesEncoded`、`qualityLimitationReason` 等) は API 仕様で定義された識別子であり、ログ中に出現してもキー名自体は日本語化しない。

## 設計方針

- `tests/` 配下の `print`・log・assert メッセージで「人間向けの説明文」を日本語化する。
- 仕様で定義された英単語 (stats のキー名、`event_type` の値、HTTP ヘッダ名など) はそのまま残す。
- 変数の `f-string` 中の英語部分も日本語に書き換える。翻訳パターンの例:
  - 状態遷移系: `print(f"send: label={label}")` → `print(f"送信: label={label}")`
  - 接続系: `print(f"Connected Sora: channel_id={id}")` → `print(f"Sora 接続完了: channel_id={id}")`
  - 切断系: `print(f"Disconnected Sora: error_code='{ec}'")` → `print(f"Sora 切断: error_code='{ec}'")`
  - イベント系: `print(f"DataChannel opened: label={label}")` → `print(f"DataChannel 開通: label={label}")`
- 例外メッセージ (`ValueError`, `NotImplementedError` 等) は本 issue の対象外。例外メッセージは Python のトレースバックに表示される開発者向け情報であり、「テストのログメッセージ」には該当しない。
- 全角・半角間スペースの規約 (AGENTS.md「全角と半角の間には半角スペースを入れる」) を満たすこと。
- 既存のテストが落ちないことを確認 (メッセージ文字列に対する assert が無いことを grep で確認する)。
- 1 ファイル単位でコミットを分けるか否かは `shiguredo-git` スキルの粒度に従う。

## 完了条件

- `rg -n "print\(" tests/` の結果から、人間向けに書かれた英文メッセージ (動詞・形容詞・説明文を含むもの) が検出されないこと。stats キー名と変数のみの f-string (例: `print(f"keyFramesEncoded: {v}")`) はキー名の出力であり日本語化不要。
- `tests/` 配下の assert メッセージで人間向けに書かれた英文が残らないこと。
- 既存のテストがすべて pass すること。
- メッセージ文字列に依存した assert (もしあれば) が壊れていないこと。
