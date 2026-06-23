# `buildbase.py::get_macos_osver()` に `return` 文が無く常に None を返している問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-get-macos-osver-no-return

## 目的

`buildbase.py:2249-2250` の `get_macos_osver()` は関数本体が

```python
def get_macos_osver():
    platform.mac_ver()[0]
```

の 1 行のみで `return` 文が無い。Python は最後に評価した式の値を捨て、常に `None` を返す。同じファイルの `get_windows_osver()` は対照的に `return osver + "." + ...` で値を返しており、命名規約上 `get_macos_osver()` も macOS のバージョン文字列を返す前提で書かれていることが明らかなため、これは単純な書き忘れバグである。

呼び出し側 `run.py:201, 203` は戻り値を `Platform("macos", get_macos_osver(), "arm64")` に渡しており、現状の処理パスでは macOS の osver を実際に分岐に使っていないため表面化していないが、将来 macOS の osver で分岐を切った瞬間に「常に None」が静かに誤動作を起こす。表面化前に直す。

## 優先度根拠

Medium とする。

- 現状の動作系では macOS osver が分岐ロジックに使われていないため、ユーザーから見える挙動破壊は起きていない。High ではない。
- ただし「関数名と実装が完全に矛盾している」「型ヒント無しで静かに `None` を返す」「呼び出し側はその None を `Platform` の osver フィールドに突っ込んでいる」状態は明確なバグであり、`return` を 1 行足すだけで直せる。放置する理由が無い。
- macOS の osver で何か分岐したくなったとき、原因に気付くまでに無駄なデバッグ時間を消費する。早めに直しておく方が安い。
- 「常に None を返している既知の関数」を残すこと自体が broken windows であり、Low ではなく Medium が妥当。

## 現状

### 関数本体

`buildbase.py:2249-2250`:

```python
def get_macos_osver():
    platform.mac_ver()[0]
```

- 戻り値の型ヒント無し。
- `platform.mac_ver()[0]` は文字列 (例: `"15.0"`) を返す式だが、その評価結果は捨てられる。
- 結果として `get_macos_osver()` は常に `None` を返す。

### 同ファイルの `get_windows_osver()` との対比

```python
def get_windows_osver():
    osver = platform.release()
    with winreg.OpenKeyEx(
        winreg.HKEY_LOCAL_MACHINE,
        "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion",
    ) as key:
        return osver + "." + winreg.QueryValueEx(key, "ReleaseId")[0]
```

明示的に文字列を返している。命名規約から `get_macos_osver()` も「macOS の osver 文字列を返す」のが意図された設計と読める。

### 呼び出し側

`run.py:201, 203`:

```python
elif target == "macos_x86_64":
    platform = Platform("macos", get_macos_osver(), "x86_64")
elif target == "macos_arm64":
    platform = Platform("macos", get_macos_osver(), "arm64")
```

`Platform` の第 2 引数 (osver) に `None` を渡している状態。これが現状の処理パスで分岐に使われていないため、ビルドや配布に影響が出ていないだけ。将来 osver を見て条件を切った瞬間に「macOS だけ常に偽」「macOS だけ常に真」が起きる可能性がある。

## 設計方針

最小修正で正しい挙動に揃える。

```python
def get_macos_osver() -> str:
    return platform.mac_ver()[0]
```

判断ポイント:

1. 戻り値の型を `str` で確定するか、`Optional[str]` を許すか。`platform.mac_ver()[0]` は macOS 以外では空文字 `""` を返す仕様なので、`str` で揃えてよい。型ヒントを `-> str` に明示する。
2. 意図的に `None` を返したい用途が将来発生するならば、その意図をコメントとして残し、`return None` を明示する。本 issue では「`return platform.mac_ver()[0]` に修正する」を採用する。
3. `run.py:201, 203` 側で `get_macos_osver()` の戻り値が空文字や `None` の可能性を考慮しなければならない場合のガードは別途検討するが、本 issue のスコープ外。

回帰防止:

- `lint` / `ty` 等で「return 文が無い関数」「最後の式が捨てられる」検出ができないかを併せて確認する。

## 完了条件

- `get_macos_osver()` が `platform.mac_ver()[0]` を返すように修正されていること。
- macOS 上で `get_macos_osver()` が文字列 (例: `"15.0"`) を返すことを目視確認できること。
- `run.py:201, 203` の `Platform("macos", get_macos_osver(), ...)` で osver に文字列が渡るようになっていること。
- 同種のミス (`return` 漏れ) を防ぐための lint / 型チェック設定の有無について方針が決まっていること。
