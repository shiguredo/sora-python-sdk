# CHANGES.md の `LIBWEBRTC_VERSIONを` の半角・全角間スペース欠落と同種違反を一掃する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-changes-md-spacing-violation
- Polished: 2026-07-30

## 目的

`CHANGES.md` の `## 2025.5.0` セクション配下に以下のエントリがあり、半角識別子と全角助詞の間に半角スペースが欠落している。

```
  - LIBWEBRTC_VERSIONを `m143.7499.1.0` に上げる
```

`LIBWEBRTC_VERSION` (半角) と `を` (全角) の間に半角スペースが無く、AGENTS.md の「全角と半角の間には半角スペースを入れること」に違反している。
本エントリは既にリリース済み (`## 2025.5.0`) のものだが、過去違反として残っている。リポジトリのプロジェクト規約に反した記述が残ること自体が「壊れた窓」になり、後続のエントリに同じ違反が再生産される。
本 issue では該当箇所を修正し、あわせて `CHANGES.md` 全体を全角・半角間スペース観点で grep して残存違反を洗い出し、まとめて修正することを目的とする。

## 優先度根拠

Medium とする。

- コード本体の挙動には影響せず、CHANGES.md の表記に限定された問題のため High ではなく Medium。
- Low ではない理由は、AGENTS.md の規約違反が過去エントリに残っている状態が Broken Windows に該当するため。

## 現状

`CHANGES.md` の `## 2025.5.0` セクション配下:

```
- [UPDATE] Sora C++ SDK のバージョンを `2025.6.1` に上げる
  - LIBWEBRTC_VERSIONを `m143.7499.1.0` に上げる
  - CMAKE_VERSION を `4.1.2` に上げる
  - @voluntas @melpon @torikizi
```

`CMAKE_VERSION を` には半角スペースが入っているのに、直前の `LIBWEBRTC_VERSIONを` だけスペースが無い。直近の `## develop` セクションを見ると `WEBRTC_BUILD_VERSION を` `BOOST_VERSION を` `CMAKE_VERSION を` などはすべて半角スペース有りで揃っているため、`LIBWEBRTC_VERSIONを` のみ単独の表記揺れと判断できる。
他の過去エントリにも同種の違反が残っている可能性があり、本 issue 対応時に全体スキャンが必要。

## 設計方針

- 該当箇所 `LIBWEBRTC_VERSIONを` を `LIBWEBRTC_VERSION を` に修正する。
- CHANGES.md 全体を以下のような正規表現相当で走査し、英数字 (`[A-Za-z0-9_]`) と全角の境界に半角スペースが無い箇所を洗い出す。
  - 例: `grep -nE '[A-Za-z0-9_\)\]\.][ぁ-んァ-ン一-龥]' CHANGES.md` のような探索を行う。
  - 逆向き (全角 → 半角) のパターンも併せて確認する。
- 検出した違反は同一コミットで修正する。バッククォート内 (`` ` `` で囲まれた箇所) はコードとして扱うため対象外とする。
- 既存リリース済みセクションのエントリ「内容」は変えず、表記のみを修正する。
- 同じ違反が再発しないよう、必要であれば `markdownlint` や独自 lint ルールの導入を別 issue として検討する余地があるが、本 issue では既存違反の解消に専念する。

## 完了条件

- `CHANGES.md` の `## 2025.5.0` セクション配下にある `LIBWEBRTC_VERSIONを` が `LIBWEBRTC_VERSION を` に修正されていること。
- CHANGES.md 全体を全角・半角間スペース観点で走査し、検出された他の違反もすべて修正されていること (バッククォート内は対象外)。
- 修正によって既存エントリの意味が変わっていないこと (内容ではなく表記のみの修正)。
