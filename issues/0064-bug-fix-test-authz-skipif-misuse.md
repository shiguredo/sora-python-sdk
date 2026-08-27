# tests/test_authz.py の pytest.mark.skipif の誤用を skip に修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-test-authz-skipif-misuse
- Polished: 2026-07-28

## 目的

`tests/test_authz.py:7` で `@pytest.mark.skipif(reason="Sora C++ SDK 側の対応が必要")` というデコレータが書かれているが、これは `skipif` の誤用である。
`skipif` は **条件式が真のときだけ skip する** マーカで、第 1 引数 (condition) が必須。`reason` だけを与えると、pytest のバージョンによって以下の挙動になる。

- 旧来の pytest では `reason` を condition と誤解釈し、文字列の truthiness で常に skip される (たまたま動く)。
- 新しい pytest (9.x 系等) ではシグネチャ厳格化により `TypeError` や `Failed` で fail する可能性がある。

「常に skip したい」が意図であれば `@pytest.mark.skip(reason=...)` を使うのが正しい。
このテストは「Sora C++ SDK 側の対応が必要」で常に skip させたい意図であることがコメントから明白なので、正しい API に修正する。

## 優先度根拠

Medium とする。

- 現状の pytest バージョンでは「たまたま動いている」可能性が高く、即時の CI 失敗は発生していない。
- ただし pytest のバージョンアップで突然 CI が赤くなるリスクがある。`uv sync --upgrade` を日常的に行うこのリポジトリでは現実的なリスク。
- 「skip すべきテストが実は実行されてしまう」あるいは「テスト収集時に TypeError で落ちる」のどちらも、エンジニアが意図しない結果を生む可能性があり、放置すべきでない。
- 一方、現に SDK 機能を壊すバグではないので High ではない。

## 現状

`tests/test_authz.py:7` の実装。

```python
@pytest.mark.skipif(reason="Sora C++ SDK 側の対応が必要")
def test_sendonly_authz_video_true(settings):
    ...
```

正しい API は次のいずれか。

- 常に skip する: `@pytest.mark.skip(reason="...")`
- 条件付き skip: `@pytest.mark.skipif(<condition>, reason="...")`

本テストは「Sora C++ SDK 側の対応が必要」で実装そのものが未着手のため、常に skip が妥当。

## 設計方針

1. デコレータを `@pytest.mark.skip(reason="Sora C++ SDK 側の対応が必要")` に変更する。
2. 合わせて以下の規約整備を検討する (本 issue のスコープ外でも可。CODEBASE.md 等への追記候補)。
   - `skip` / `xfail` の `reason` には「対応が必要な PR 番号」や「対応すべき外部 SDK の状態」を書く。
   - Sora C++ SDK 側の対応待ちは `xfail(strict=True)` でなく `skip` を使う (xfail は「失敗することを期待する」マーカで、未実装機能には不適切)。
3. リポジトリ全体で同種の `skipif(reason=...)` 誤用が無いかを `grep` で確認し、見つかれば同じ修正を当てる。

## 完了条件

- `tests/test_authz.py:7` が `@pytest.mark.skip(reason="Sora C++ SDK 側の対応が必要")` になっている。
- `uv run pytest --collect-only tests/test_authz.py` がエラー無く収集できる。
- リポジトリ全体に `pytest.mark.skipif(reason=` の誤用パターンが残っていない。
