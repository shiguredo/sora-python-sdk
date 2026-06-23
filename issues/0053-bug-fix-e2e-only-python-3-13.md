# E2E テストの Python バージョン matrix が 3.13 のみで 3.12 / 3.14 が検証されていない問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-e2e-only-python-3-13

## 目的

`.github/workflows/e2e-test.yml` の Python バージョン matrix が 3.13 のみとなっており、`pyproject.toml` の `requires-python` で公式にサポートしている 3.12 と 3.14 が E2E テストで一切検証されていない。さらに schedule トリガー自体もコメントアウトされており、「TODO: schedule 時には全部でテストする」というコメントだけが残った状態になっている。

サポート対象として宣言している全 Python バージョンが、リリース前に E2E で動作確認される状態を取り戻す。

## 優先度根拠

Medium とする。

- `requires-python` で 3.12 / 3.13 / 3.14 をサポートすると宣言しているにもかかわらず、E2E では 3.13 しか動かしていない。サポート宣言と検証実態の不一致は、ユーザーが 3.12 / 3.14 で踏むバグを CI で取り逃すリスクに直結する。
- 一方で開発フローを即座にブロックしている問題ではない。日常的な PR ごとに全バージョンを回す必要は薄く、release 直前または定期 schedule で吸収するのが妥当。High に上げるほどの緊急性は無い。
- 「TODO だけ残してコメントアウトする」状態は broken windows であり、長期間放置すると schedule 自体の存在を皆が忘れる。早めに方針を明文化して TODO を解消する。

## 現状

### Python バージョン matrix が 3.13 のみ

`.github/workflows/e2e-test.yml:107-111`:

```yaml
        python_version:
          # TODO: schedule 時には全部でテストする
          # - "3.12"
          - "3.13"
          # - "3.14"
```

3.12 と 3.14 がコメントアウトされていて、`workflow_dispatch` で手動実行しても、`push` で develop に流しても 3.13 でしか走らない。

### schedule トリガー自体がコメントアウトされている

`.github/workflows/e2e-test.yml:18-21`:

```yaml
  # schedule:
  #   # UTC の 01:00 は JST だと 10:00 。
  #   # 1-5 で 月曜日から金曜日
  #   - cron: "0 1 * * 1-5"
```

TODO のコメントが指している「schedule 時」のトリガー自体が現状無効。schedule を有効にしないまま「schedule 時には全部でテストする」と書き残しているため、TODO に到達するイベントが永遠に来ない。

### `requires-python` でサポート宣言

`pyproject.toml` の `requires-python` は 3.12 / 3.13 / 3.14 をサポート対象として宣言している。E2E でカバーされていない 3.12 / 3.14 でユーザーが踏むバグを CI が拾えない構造になっている。

## 設計方針

以下のいずれか、または組み合わせで TODO 状態を解消する。設計判断は実装時に行う。

1. schedule トリガーを復活させる。`schedule` のコメントアウトを外し、3.12 / 3.13 / 3.14 すべてを matrix に含めた状態で平日朝に定期実行する。push / workflow_dispatch では現状どおり 3.13 のみで回し、CI 時間を抑える。
2. schedule を有効化しない代わりに、`workflow_dispatch` の inputs として「全 Python バージョンで走らせる」スイッチを追加する。release 直前は手動で全 matrix を回し、release 直前にだけ全バージョン検証が走る経路を明文化する。
3. リリース直前のチェックリストに「3.12 / 3.13 / 3.14 全 matrix で E2E を回す」を明記する。CI 設定だけで担保せず手順としても残す。

いずれの方針でも、`requires-python` で宣言したバージョンとリリース前 E2E の検証範囲は揃える。`# TODO:` のコメントは設計判断の結果として削除または明確な手順への置き換えを行い、コメントだけ残った状態にしない。

## 完了条件

- `requires-python` で宣言した Python バージョン (3.12 / 3.13 / 3.14) のすべてが、release 直前までに少なくとも 1 度は E2E で実行される経路が存在すること。
- どの経路でどのバージョンが走るかが workflow ファイルまたはリリース手順書から読み取れること。「TODO: schedule 時には全部でテストする」のような、トリガー側が無効化された TODO コメントが残っていないこと。
- 通常の push / PR で CI 時間が極端に伸びないこと (3.13 のみで回す経路は維持してよい)。
