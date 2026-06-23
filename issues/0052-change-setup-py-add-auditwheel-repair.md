# `setup.py` の manylinux タグ手動指定をやめて `auditwheel repair` ベースに切り替える

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/setup-py-add-auditwheel-repair

## 目的

`setup.py` の `bdist_wheel.get_tag` は、Ubuntu 22.04 / 24.04 (および Jetson / Raspberry Pi OS) について manylinux タグを手動で文字列指定している。

- Ubuntu 22.04 → `manylinux_2_31_*`
- Ubuntu 24.04 → `manylinux_2_35_*`
- Jetson → `manylinux_2_17_aarch64.manylinux2014_aarch64`
- Raspberry Pi OS → `manylinux_2_35_aarch64`

これらの値は「ビルド環境の glibc バージョン」を経験的に書いているだけで、実際の wheel が依存している glibc / 共有ライブラリの実態を検査していない。
そのため、次の 2 種類の壊れ方が起きうる。

1. 実際の依存より緩いタグ (例: `manylinux_2_31_*` だが内部で 2.35 のシンボルを使っている) を付けると、より古い環境で pip install したときに ImportError になる。
2. 実際の依存より厳しいタグ (例: 本来 `manylinux_2_28_*` で動くが `manylinux_2_31_*` と宣言してしまっている) を付けると、本来動くはずの環境で pip install できなくなる。

`auditwheel repair` は wheel の依存実体 (glibc バージョン、共有ライブラリ) を解析して適切な manylinux タグを付与し、必要なら共有ライブラリの同梱・パッチも行う標準ツールであり、PyPI 上で配布する Linux wheel の事実上の作法。本 issue では `auditwheel repair` を CI に導入し、実依存からタグを決める経路に切り替えることを目的とする。

## 優先度根拠

Medium とする。

- 現在は経験則的に手動指定が当たっており、ユーザーから明確な障害報告は無いと見られる。しかし libwebrtc / Sora C++ SDK / Boost のアップグレードに伴って実際に必要な glibc バージョンが変動する可能性があり、潜在的な互換性壊れの温床として残し続ける合理性は無い。
- 一方、`auditwheel repair` 導入は wheel に共有ライブラリを同梱する経路を含むため、設計判断 (どの依存を含めるか / `LD_LIBRARY_PATH` で外部解決させるか) を伴う。issue 0006 で計画されている CI 整理と歩調を合わせて進める必要があり、即時対応が必須ではない。

## 現状

`setup.py` の 23-39 行:

```python
plat = None
additional_files = []
if target_platform.os == "jetson":
    plat = "manylinux_2_17_aarch64.manylinux2014_aarch64"
elif target_platform.os == "ubuntu" and target_platform.arch == "armv8":
    if target_platform.osver == "22.04":
        plat = "manylinux_2_31_aarch64"
    if target_platform.osver == "24.04":
        plat = "manylinux_2_35_aarch64"
elif target_platform.os == "ubuntu" and target_platform.arch == "x86_64":
    if target_platform.osver == "22.04":
        plat = "manylinux_2_31_x86_64"
    if target_platform.osver == "24.04":
        plat = "manylinux_2_35_x86_64"
elif target_platform.os == "raspberry-pi-os":
    plat = "manylinux_2_35_aarch64"
    additional_files += ["libcamerac.so"]
```

`bdist_wheel.get_tag` の中で `plat` を強制的に上書きしており、wheel タグ自体は付与できるが、wheel の中身が宣言したタグと整合しているかの保証は無い。
`auditwheel show` / `auditwheel repair` は CI 内で一度も呼ばれておらず、wheel の依存実体は誰も検査していない。

加えて、Raspberry Pi OS の wheel は `libcamerac.so` を同梱しているが、これも `auditwheel repair` 相当の処理を独自実装しているとみなせる。auditwheel ベースに揃えれば「同梱物の選定」も統一できる可能性がある。

## 設計方針

以下の手順で対応する。本 issue では断定的なステップ順までは確定させない。

1. Linux 系プラットフォーム (Ubuntu 22.04 / 24.04 x86_64 / armv8、Jetson、Raspberry Pi OS) の CI ビルドジョブに `auditwheel show` を追加し、現状の wheel が実際にどの manylinux タグになるべきかを把握する。
2. その上で `auditwheel repair --plat <タグ>` を導入し、生成された repaired wheel を最終成果物として artifact / PyPI に上げる経路に切り替える。
   - Jetson のように Tegra / NVIDIA の共有ライブラリは wheel に同梱しない方針が必要なら、auditwheel の `--exclude` オプションで除外する。
   - Raspberry Pi OS の `libcamerac.so` も同様に「同梱するか除外するか」を改めて整理する。
3. `setup.py` 側の手動タグ指定は、auditwheel に置き換えて不要となった範囲を削除する。完全削除が難しい場合 (Jetson の独自タグなど) は、削除できない理由をコメントで残す。
4. CI 整理は issue 0006 の計画と連動するため、独立に進める部分と統合する部分の境界を作業時に判断する。

## 完了条件

- Linux 系の wheel ビルドジョブで `auditwheel repair` (もしくは同等の検査) が実行されており、wheel の manylinux タグが実依存と整合していること。
- 同梱共有ライブラリの方針 (Jetson の Tegra / NVIDIA、Raspberry Pi OS の `libcamerac.so` 等) が明確化されていること。
- `setup.py` から「手動でタグ文字列を書く」コードが極力削減されており、残った部分には残す理由がコメントされていること。
- 修正後の wheel を pip install したときに、サポート対象環境 (CHANGES / README に記載のバージョン) で従来どおり import / 動作すること。
- issue 0006 (CI 整理) と矛盾しない形で取り込まれていること。
