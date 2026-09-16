# README と SKILL.md を sora-rust-sdk ベースへ追従させる

- Created: 2026-09-16
- Completed: -
- Branch: feature/update-docs-for-rust-migration
- Polished: {YYYY-MM-DD}

## 目的

`README.md` と `skills/sora-python-sdk/SKILL.md` の Sora C++ SDK ベースである旨の記述を、sora-rust-sdk + PyO3 + maturin の実態に合わせて更新する。あわせて開発者向けドキュメントを新しいビルド手順へ追従させる。

## 現状

- `README.md` の概要は「[Sora C++ SDK](https://github.com/shiguredo/sora-cpp-sdk) をベースにしています」と述べている。特徴の一覧にも「Sora C++ SDK ベース」とあり、HWA 対応の説明が Sora C++ SDK の README を参照している。
- `skills/sora-python-sdk/SKILL.md` は「Sora C++ SDK ベースの nanobind バインディング」と述べている。
- `docs/migration-to-sora-rust-sdk.md` と `docs/sora-rust-sdk-investigation.md` を第 1 段で追加した。移行の進行に合わせて内容を更新する必要がある。
- 移行後は CMake と sysroot 構築が不要になり、ビルドは maturin になる。開発手順 (README の開発者向けの節) は現行の `run.py` / `dev.py` を前提にしている。
- `.rst` と `.md` の変更は変更履歴に反映しない (`shiguredo-changelog` 規約)。

## 設計方針

- `README.md` と `skills/sora-python-sdk/SKILL.md` の Sora C++ SDK ベースである旨の記述を、sora-rust-sdk ベースへ書き換える。
- HWA 対応の説明は、sora-rust-sdk が対応する符号化器の一覧へ合わせる。Sora C++ SDK の README への参照を残すかどうかは、実態に合わせて判断する。
- 開発者向けの手順を maturin と uv のコマンドへ書き換える。削除された `run.py` / `dev.py` への参照を残さない。
- `docs/migration-to-sora-rust-sdk.md` の完了条件を満たした項目に印を付け、移行の完了時に issue 0098 を closed にできる状態にする。
- ドキュメントの表記は `shiguredo-doc` 規約に従う。全角と半角の間に半角スペースを入れる。
- 値の合成、引数の破棄、別方式による代替、意図しない公開面からの消失が残っていないことを、ドキュメントの記述と実装の両面で確認する。残っている場合は実装側の issue へ差し戻す。

## 完了条件

- `README.md` に Sora C++ SDK ベースである旨の記述が残っていないこと。
- `skills/sora-python-sdk/SKILL.md` に Sora C++ SDK ベースである旨の記述が残っていないこと。
- 開発者向けのビルド手順が maturin と uv のコマンドになっていること。
- 削除されたファイル (`run.py` / `dev.py` / `buildbase.py` / `sysroot_builder.py` 等) への参照が残っていないこと。
- `docs/migration-to-sora-rust-sdk.md` の完了条件の達成状況が反映されていること。
- `CHANGES.md` の `## develop` の `[CHANGE]` エントリが移行の最終的な差分を表していること。`.md` と `.rst` の変更自体は変更履歴に反映しないため、エントリは本 issue で新規に追加するのではなく、移行で機能に影響する変更を加えた issue が追加した内容を確認して不足を補う。

## 依存

- 先行: ビルド基盤を maturin へ置き換える issue、CI の issue、テスト移行の issue、既存 issue の処遇の issue。
- 上流: 無し。
- 後続: 無し。本 issue の完了後に親 issue を closed にする判断を行う。

## 解決方法
