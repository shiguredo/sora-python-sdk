# `tests/client.py` の fake video スレッドが disconnect 時に AssertionError を上げる問題を修正する

- Created: 2026-09-17
- Completed: -
- Branch: feature/fix-fake-video-thread-race
- Polished: {YYYY-MM-DD}

## 目的

E2E テストの共通ヘルパである `tests/client.py` の `SoraClient` で、fake video を送るスレッド `_fake_video_loop` と `_on_disconnect` が競合し、スレッド内で `AssertionError` が発生する。pytest はこれを `PytestUnhandledThreadExceptionWarning` として報告する。

テストの合否には影響しないが、テストログが警告で汚れ、警告をエラーとして扱う運用にすると落ちる。テストヘルパとして、disconnect と競合しても例外を上げない状態にする。

## 現状

- `_fake_video_loop` は `self._video_source` が `None` でないことを確認したあと、`assert isinstance(self._video_source, SoraVideoSource)` で型を絞り込んでから `on_captured` を呼ぶ。属性を複数回読み出しており、読み出しの間に `_on_disconnect` が割り込む余地がある。
- `_on_disconnect` は `self._disconnected.set()` のあとに `self._video_source = None` を代入し、そのあと `self._fake_video_thread.join(timeout=10)` する。つまり、スレッドの終了を待つ前に属性を差し替える。
- このため「`_fake_video_loop` が `None` でないと確認した直後」に `_on_disconnect` が `None` を代入すると、`isinstance` のアサーションが `None` を見て `AssertionError` になる。
- 実測: `uv run pytest tests/ -n auto` を複数回実行すると、1 回あたり 1 〜 6 件の警告が出る。警告は `tests/test_simulcast.py` や `tests/test_key_frame_request.py` など fake video を使うテストに帰属し、トレースバックの末尾は常に `_fake_video_loop` の `isinstance` の行である。
- 例外はスレッド内で完結するため、テスト結果と終了コードには影響しない。

## 設計方針

- `_fake_video_loop` で `self._video_source` をローカル変数に 1 回だけ読み出し、`None` の確認と `isinstance` による絞り込みと `on_captured` の呼び出しを、そのローカル変数に対して行う。属性を 1 回しか読まなければ、読み出しの間に `_on_disconnect` が代入する窓が生まれない。
- `assert isinstance(...)` は型の絞り込み（属性の型は `SoraVideoSource | SoraTrackInterface | None`）として必要なので残す。
- `_on_disconnect` の後始末の順序と意味は変更しない。スレッドの停止は `_disconnected` で行っており、`_video_source` の解放は参照を手放すためのものなので、読み出しをローカル変数に寄せれば競合は解消する。
- `_fake_audio_loop` は `_audio_source` を解放しないため同じ競合は無く、変更しない。
- `SoraVideoSource` 以外の映像ソース（libcamera）を使う場合の型の扱いは変更しない。

## 完了条件

- `_fake_video_loop` が `self._video_source` を読み出したあとに `_on_disconnect` が `None` を代入しても `AssertionError` にならないこと（属性の読み出しが 1 回であることをコードで確認する）。
- `uv run pytest tests/ -n auto` を複数回実行して `PytestUnhandledThreadExceptionWarning` が発生しないこと。
- 既存のテストが全て pass すること。
