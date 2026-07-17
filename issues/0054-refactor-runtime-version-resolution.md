# runtime version 解決を distribution metadata に統一する

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: -
- Model: GPT-5
- Branch: feature/refactor-runtime-version-resolution
- Polished: 2026-07-17

## 目的

`sora_sdk.__version__` の runtime 解決を installed distribution metadata に統一し、repository directory の階層数に依存してトップレベル `VERSION` を探す fallback を削除する。

source version の単一情報源はトップレベル `VERSION`、installed runtime の単一情報源は wheel / editable install の `.dist-info` metadata とし、同じ値を package data として二重同梱しない。

## 優先度根拠

- 通常の wheel install では `importlib.metadata.version('sora_sdk')` が成功するため、直ちに公開を止める問題ではない。
- metadata が無い壊れた環境で repository 外の任意階層を読む fallback は、正しい version に見える誤動作を起こし得るため整理が必要である。

## 前提

- 0001 と 0051 の完了後に実装する。
- 0001 が scikit-build-core の dynamic version provider でトップレベル `VERSION` を distribution metadata に反映する。
- 0051 が sdist にトップレベル `VERSION` を含め、sdist だけから同じ metadata の wheel を生成できることを検証する。

## 現状

現行 `src/sora_sdk/__init__.py` は `importlib.metadata.version('sora_sdk')` が `PackageNotFoundError` になると、`__file__` から `dirname` を 3 回適用して repository root と仮定し、`VERSION` を読む。

この fallback は source tree 直下からの直接 import にしか成立しない。wheel の package directory にトップレベル `VERSION` は存在せず、PyInstaller / Nuitka 等で metadata を除外した bundle も正規の distribution 契約を満たさない。旧 issue が想定した `setup.py package_data` への `VERSION` 追加は、0001 で `setup.py` 自体を削除するため適用できない。

## 設計方針

### version 契約

- build / sdist 入力は repository root の `VERSION` とする。
- scikit-build-core が `VERSION` を Core Metadata の `Version` と wheel filename に反映する。
- installed wheel と editable install の `sora_sdk.__version__` は `importlib.metadata.version('sora_sdk')` だけから取得する。
- `PackageNotFoundError` の場合は `unknown` とし、filesystem を上位へ探索しない。
- package directory に `VERSION` / `_version.py` を複製生成せず、`importlib.resources` fallback も追加しない。

source checkout から project を install せず直接 import する使い方は distribution runtime 契約の対象外とする。その場合に偶然 root `VERSION` を発見して正規 install と同じように見せない。

### 実装

`src/sora_sdk/__init__.py` から `os` import、`dirname` / `exists` / `open` による fallback を削除する。`PackageNotFoundError` だけを捕捉して `__version__ = 'unknown'` とする。metadata の破損や予期しない例外を `unknown` に握りつぶさない。

`tests/test_version.py` は次を実物で検証する。

- build wheel を clean environment に install し、`sora_sdk.__version__`、`importlib.metadata.version('sora_sdk')`、トップレベル `VERSION` が一致する。
- editable install でも同じ 3 値が一致する。
- distribution metadata を持たない source package の隔離 copy を `PYTHONPATH` から import すると `unknown` になり、repository root の `VERSION` を探索しない。
- wheel 内に重複した `sora_sdk/VERSION` / `_version.py` が無い。

mock / stub や `importlib.metadata.version` の monkeypatch は使わず、clean virtual environment と実際の wheel / editable install / 隔離 source copy を使う。

## 完了条件

- wheel install と editable install の `sora_sdk.__version__` が distribution metadata とトップレベル `VERSION` に一致する。
- `src/sora_sdk/__init__.py` が親 directory を探索せず、`PackageNotFoundError` 以外を握りつぶさない。
- metadata の無い隔離 source import が `unknown` を返す。
- wheel に version 値の複製 file を同梱しない。
- 0051 の sdist 単独 smoke でも同じ version 契約を検証する。

## 解決方法

1. runtime version 解決を `importlib.metadata` に限定する。
2. wheel / editable / metadata 無し source import の実物 test を追加する。
3. wheel 内容に version 複製 file が無いことを確認する。
4. `CHANGES.md` の `## develop` に次を追加する。

```
- [REFACTOR] runtime version 解決を distribution metadata に統一する
  - @voluntas
```

## ロールバック

問題がある場合も親 directory を探索する旧 fallback は復活させない。supported install 経路の metadata 生成を forward fix し、metadata を同梱できない bundle は support 対象外として明示する。
