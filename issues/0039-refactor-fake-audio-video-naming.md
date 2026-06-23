# テストヘルパの `fake_audio` / `fake_video` 命名をモック・スタブと紛らわしくない名前に変える

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-fake-audio-video-naming

## 目的

AGENTS.md L16 に「モックやスタブは絶対に利用しないこと」と明記されているが、`tests/client.py` で `fake_audio` / `fake_video` という命名が広範に使われており、規約と矛盾しているように読める。実体は SDK 正規 API (`SoraAudioSource.on_data` / `SoraVideoSource.on_captured`) を使った合成データ送出であって、モック・スタブではない。

この「実体は合成データ送出だが命名がモックを連想させる」という不一致を解消し、規約と実装の意図が一致した状態にする。

## 優先度根拠

Medium とする。

- 機能には影響しない命名リファクタだが、規約と紛らわしい状態は新規参加者の混乱と、規約違反のレビュー指摘ループを生む。
- High ではない理由は、テスト挙動・本番コードには影響しないため。
- Low ではない理由は、AGENTS.md の規約と直接ぶつかって見える点で「Broken Windows」に該当するため。

## 現状

`tests/client.py` 該当箇所:

- L231: `return self.connect(fake_audio=bool(self._audio), fake_video=bool(self._video))`
- L238: `def connect(self, fake_audio=False, fake_video=False) -> "SoraClient":`
- L240-247: `if fake_audio: self._fake_audio_thread = threading.Thread(...)` / `if fake_video: ...`
- L364: `def _fake_audio_loop(self):`
- L370: `def _fake_video_loop(self):`
- L486-490: `self._fake_audio_thread.join(...)` / `self._fake_video_thread.join(...)`

実装内容を確認すると、

- `_fake_audio_loop` は `numpy.zeros((320, 1), dtype=numpy.int16)` を `self._audio_source.on_data` に渡す。
- `_fake_video_loop` は `numpy.random.randint` で生成したフレームを `self._video_source.on_captured` に渡す。

どちらも SDK 正規 API を呼び出しているだけで、SDK 内部の差し替えはしていない。すなわちモック (差し替え) でもスタブ (実装の代用品) でもなく、テスト用の合成入力データである。

`tests/` 配下を `rg -n "fake_audio|fake_video|_fake_audio|_fake_video" tests/` で検索すると、`tests/client.py` 以外のテストファイルからもこの名前を経由して呼ばれている。

## 設計方針

- 命名を `synthetic_audio` / `synthetic_video` (または `generated_audio` / `generated_video`) に変更する。本 issue では `synthetic_*` を第一候補とする。
- 変更対象:
  - 引数 `fake_audio` / `fake_video` → `synthetic_audio` / `synthetic_video`
  - 内部属性 `_fake_audio_thread` / `_fake_video_thread` → `_synthetic_audio_thread` / `_synthetic_video_thread`
  - メソッド `_fake_audio_loop` / `_fake_video_loop` → `_synthetic_audio_loop` / `_synthetic_video_loop`
  - 上記を呼ぶテストファイル側 (キーワード引数で渡している箇所すべて)
- `tests/client.py` の docstring に「`synthetic_*` は SDK 正規 API (`SoraAudioSource.on_data` / `SoraVideoSource.on_captured`) を使った合成データ送出であり、モック・スタブではない」旨を明記する。
- 既存テストが破綻しないよう、テストファイル側の呼び出しもすべて更新する (キーワード引数のため一括置換可能)。

## 完了条件

- `rg -n "fake_audio|fake_video" tests/` の結果が 0 件になること。
- `tests/client.py` の docstring または冒頭コメントに「合成データであり SDK 正規 API を使うのでモック・スタブではない」旨が日本語で書かれていること。
- 既存のテストがすべて pass すること。
