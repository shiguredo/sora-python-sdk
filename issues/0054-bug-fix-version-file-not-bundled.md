# wheel に `VERSION` ファイルが同梱されず `__init__.py` のフォールバックが壊れやすい問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-version-file-not-bundled

## 目的

`src/sora_sdk/__init__.py` の `__version__` 解決には 2 段階のフォールバックがある。インストール済みパッケージなら `importlib.metadata.version("sora_sdk")` を使い、開発環境では `VERSION` ファイルを直接読む。ところが、

- フォールバック側が `os.path.dirname` を 3 重で重ねており、`src/sora_sdk/__init__.py` → `<repo>/VERSION` という前提に強く依存している。
- `setup.py` の `package_data` に `VERSION` が含まれていないため、wheel 化された場合 wheel 内の `sora_sdk` パッケージ内に `VERSION` が同梱されない。
- `MANIFEST.in` には `include VERSION` があるが、これは sdist 用であり wheel の `package_data` を補わない。

結果として、`importlib.metadata` が失敗するシナリオ (例: editable インストールが壊れている、PyInstaller / Nuitka 等で bundle した、メタデータが落ちた) に陥った時、`VERSION` のパスがズレて `"unknown"` まで落ちる、あるいは存在しないパスを読みに行く。`__version__` が「壊れにくい単一の経路」で取れる状態を取り戻す。

## 優先度根拠

Medium とする。

- 通常の pip インストールでは `importlib.metadata` で `__version__` が取れるため、現在ユーザー影響が表面化しているわけではない。High ではない。
- ただし「フォールバック経路が現状でも論理的に壊れている」状態であり、editable インストールの壊れや bundle ツール経由で起きる事故を放置すると debug が難しくなる。`__version__` はバージョン管理・サポート問い合わせの基準なので、`"unknown"` に落ちる経路は減らしておきたい。
- 修正は `package_data` への 1 エントリ追加と `__init__.py` の数行差し替えで済む。コストが低い割に堅牢性が上がるため Low ではなく Medium。

## 現状

### `__init__.py` の fallback パス計算

`src/sora_sdk/__init__.py:14-21`:

```python
_version_file = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "VERSION"
)
if os.path.exists(_version_file):
    with open(_version_file) as f:
        __version__ = f.read().strip()
else:
    __version__ = "unknown"
```

- `__file__` = `<root>/src/sora_sdk/__init__.py`
- `dirname` 3 重 = `<root>` (`src/sora_sdk` → `src` → `<root>`)
- そこから `VERSION` を読む

つまりリポジトリ直下の `VERSION` を読む前提で、wheel に同梱された場合や別構成でインストールされた場合に追従できない。`os.path.dirname` を重ねるアプローチは、相対構造の変化に対する耐性が無い。

### `setup.py` の `package_data` に `VERSION` が無い

`setup.py:54-58`:

```python
packages=["sora_sdk"],
package_dir={"": "src"},
package_data={
    "sora_sdk": ["sora_sdk_ext.*", *additional_files],
},
```

`VERSION` が `package_data` に含まれていないので wheel 内の `sora_sdk/` 配下に `VERSION` が同梱されない。仮に fallback 側が `sora_sdk` パッケージ内の `VERSION` を読む実装に直されていても、wheel では読み出せない。

### `MANIFEST.in` は sdist 用

`MANIFEST.in:4`:

```
include VERSION
```

これは sdist にトップレベル `VERSION` を含めるための指定で、wheel の `package_data` を補完しない。

## 設計方針

`__version__` を 1 つの確かな場所から読む構造に統一する。

1. `setup.py:54-58` の `package_data` に `"VERSION"` を追加し、wheel の `sora_sdk/` パッケージ内に `VERSION` を同梱する。
2. `src/sora_sdk/__init__.py` の fallback を `importlib.resources.files("sora_sdk") / "VERSION"` を読む形に変更する。インストール済 wheel でも editable でも同じパスで読める。
3. `importlib.metadata.version` 取得経路は維持する。fallback は「メタデータが取れなかったときのバックアップ」として残し、wheel 内同梱の `VERSION` のみを参照する。
4. `MANIFEST.in` の `include VERSION` は sdist 同梱用としてそのまま残す。

最終形は「メタデータ → パッケージ内 `VERSION` → `"unknown"`」の三段で、どの段でも実環境のパス計算に依存しない。`os.path.dirname` の 3 重を捨てる。

## 完了条件

- `pip install` 後の wheel から `sora_sdk` を import し `sora_sdk.__version__` が `VERSION` ファイルの値と一致して取得できること。
- editable インストール (`pip install -e .`) 配下でも `__version__` が正しい値を返すこと。
- `importlib.metadata` が失敗するシナリオ (PyInstaller などで bundle した状態) を再現した場合に、`__init__.py` の fallback が `os.path.dirname` の階層数に依存しない形で `VERSION` を解決できること。
- 解決経路がコメントから読み取れること (`importlib.metadata` → パッケージ内 `VERSION` の順、最終 fallback は `"unknown"`)。
