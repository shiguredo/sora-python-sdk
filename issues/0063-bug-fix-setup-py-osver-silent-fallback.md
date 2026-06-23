# setup.py の Ubuntu osver 分岐を if/elif/else にして未知バージョンを fail-fast にする

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-setup-py-osver-silent-fallback

## 目的

`setup.py` の `run_setup` 内で、Ubuntu (armv8 / x86_64) の `osver` 分岐は `if/if` の連結になっている。
分岐の対象が `"22.04"` / `"24.04"` のいずれでもない場合 (将来の `"26.04"` 等が来た場合)、`plat` は `None` のままになり、その後 `bdist_wheel.get_tag` で `plat if plat is not None else plat2` のフォールバックが発動して、ローカルプラットフォームタグの wheel が静かに生成される。

これは「クロスビルド設定が正しく適用されないまま wheel が出来る」という沈黙バグであり、CI 上では「ビルドは通ったのに PyPI 配布が壊れる」事故に繋がる。これを fail-fast に直す。

## 優先度根拠

Medium とする。

- 現状の `SORA_SDK_TARGET` 受け付け側 (`main()`) は `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` 等の文字列マッチで弾いているため、現在ビルド対象に入っていない値が `target_platform.osver` に渡ることは無い。
- ただし `main()` を拡張して新しい OS バージョンを増やしたときに `run_setup` 側を修正し忘れると、エラーにならずに「ローカルタグの wheel」が PyPI 配布候補に紛れ込む。これは PyPI の `manylinux_*` タグ衛生を壊し、最悪 PyPI へのアップロード失敗・誤配布に繋がる。
- 「沈黙のフォールバック」は早期に潰すべき種類のバグであり、Premature Optimization ではなく Broken Window として扱う。

## 現状

`setup.py:27-36` の実装は次の通り。

```python
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
```

問題点は 2 つある。

1. 内側が `if` の連続であり `elif` でない。`osver == "22.04"` のときも `osver == "24.04"` の条件を再評価しているだけで実害は無いが、意図が分かりにくい。
2. 内側に `else` が無いため、`osver` が `"22.04"` / `"24.04"` 以外のとき `plat = None` のまま素通りする。
   - `bdist_wheel.get_tag` で `return impl, impl, plat if plat is not None else plat2` というフォールバックがあるため、`plat2` (ローカルマシンのタグ) で wheel が作られる。

## 設計方針

`setup.py:27-36` を `if/elif/else: raise` 形式に直し、未知の `osver` で fail-fast にする。

```python
elif target_platform.os == "ubuntu" and target_platform.arch == "armv8":
    if target_platform.osver == "22.04":
        plat = "manylinux_2_31_aarch64"
    elif target_platform.osver == "24.04":
        plat = "manylinux_2_35_aarch64"
    else:
        raise ValueError(f"Unsupported ubuntu armv8 version: {target_platform.osver}")
elif target_platform.os == "ubuntu" and target_platform.arch == "x86_64":
    if target_platform.osver == "22.04":
        plat = "manylinux_2_31_x86_64"
    elif target_platform.osver == "24.04":
        plat = "manylinux_2_35_x86_64"
    else:
        raise ValueError(f"Unsupported ubuntu x86_64 version: {target_platform.osver}")
```

合わせて `main()` 側の `target` 文字列マッチも 1 箇所に集約できるか検討する (本 issue のスコープ外で良い)。
また、`bdist_wheel.get_tag` の `plat if plat is not None else plat2` フォールバック自体を残すかは別件 (raspberry-pi-os 等で `plat` が常に埋まる構造に出来るなら除去できる) として扱う。

## 完了条件

- `setup.py:27-36` が `if/elif/else` 構造になっている。
- 未知の `osver` が渡ったときに `ValueError` で即座に失敗する。
- CI の既存ビルド (`ubuntu-22.04_armv8`, `ubuntu-24.04_armv8`, `ubuntu-22.04_x86_64`, `ubuntu-24.04_x86_64`) が全て green のまま通る。
