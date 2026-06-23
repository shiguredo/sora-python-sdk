# tests/client.py の disconnect 関連属性の命名不整合と未初期化を解消する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-client-disconnect-attr-not-initialized

## 目的

`tests/client.py` の `SoraClient` クラスで、`__init__` が初期化する disconnect 関連属性と、`_on_disconnect` / `property` が参照する属性の名前が一致していない。

- `__init__` (200-201 行) では `_disconnect_error_code` / `_disconnect_error_message` を `None` で初期化する。
- 一方 `_on_disconnect` (477-478 行) では別名 `_disconnect_code` / `_disconnect_reason` に代入する。
- `disconnect_code` / `disconnect_reason` の `property` (357-362 行) も同じく `_disconnect_code` / `_disconnect_reason` を参照する。

このため、`_on_disconnect` が呼ばれる前に property を読むと **AttributeError** で落ちる。
さらに `__init__` で初期化される `_disconnect_error_code` / `_disconnect_error_message` は読み出し箇所が 1 つも無く、完全なデッドコードになっている。

加えて、`_on_set_offer` (439 行) で代入される `_offer_ignore_disconnect_websocket` も `__init__` で初期化されておらず、`offer` 受信前に参照されると同様に AttributeError になる。

これら命名不整合・未初期化を整理し、テストヘルパとしての堅牢性を確保する。

## 優先度根拠

Medium とする。

- 現状のテストは「`_on_disconnect` 後に property を読む」「`offer` 受信後に `_offer_ignore_disconnect_websocket` を読む」運用で偶然成立しているため、ほとんどのテストは通る。
- ただし、これからテストを追加する開発者が「disconnect 前に状態を確認したい」「offer 待たずに値を確認したい」といった素直なテストを書いた瞬間に AttributeError で落ちる。テストヘルパとして「初期状態でも安全に読める」ことは基本要件。
- デッドコード (`_disconnect_error_code` / `_disconnect_error_message`) を残すと、「名前が違う属性に何かを期待している」誤読を将来の編集者が起こしうる。Broken Window として早期に潰すべき。
- 一方、現に CI を赤くしているわけではないので High ではない。

## 現状

`tests/client.py:200-201` (`__init__`):

```python
self._disconnect_error_code: int | None = None
self._disconnect_error_message: str | None = None
```

`tests/client.py:357-362` (`property`):

```python
@property
def disconnect_code(self) -> int | None:
    return self._disconnect_code

@property
def disconnect_reason(self) -> str | None:
    return self._disconnect_reason
```

`tests/client.py:477-478` (`_on_disconnect`):

```python
self._disconnect_code = error_code.value
self._disconnect_reason = message
```

`tests/client.py:439` (`_on_set_offer`):

```python
self._offer_ignore_disconnect_websocket = message["ignore_disconnect_websocket"]
```

`_offer_ignore_disconnect_websocket` は `__init__` のどこにも出てこない。

## 設計方針

1. 命名を `_disconnect_code` / `_disconnect_reason` に統一する。
   - `__init__` の `_disconnect_error_code` / `_disconnect_error_message` を `_disconnect_code` / `_disconnect_reason` にリネームし、`None` で初期化する。
   - 旧名 `_disconnect_error_code` / `_disconnect_error_message` は読み出し箇所が無いデッドコードなので、リネームではなく削除する (退路を断ち、二度と誤読されないようにする)。
2. `_offer_ignore_disconnect_websocket` も `__init__` で `None` 初期化する。
   - 既存の `self._ignore_disconnect_websocket: bool | None = None` (`switched` 時に書き換えられる) と並べて、`self._offer_ignore_disconnect_websocket: bool | None = None` を追加する。
3. 追加で以下も確認する。
   - `client.py` 全体に「`_on_<event>` まで値が無い」属性が他にも無いか grep で洗い出す。あれば同様に `__init__` で `None` 初期化する。
   - property を読んだ側のテストが「`None` チェック」を意識しているか確認する (型注釈 `int | None` で `None` を返してよい構造なので、テスト側で `assert is not None` を入れる責務はテスト側)。

## 完了条件

- `_on_disconnect` 前に `client.disconnect_code` / `client.disconnect_reason` を読んでも AttributeError にならず `None` が返る。
- `offer` 受信前に `client._offer_ignore_disconnect_websocket` を読んでも AttributeError にならず `None` が返る。
- `__init__` に `_disconnect_error_code` / `_disconnect_error_message` というデッド属性が残っていない。
- 既存テスト (`uv run pytest tests/`) が全て pass する。
