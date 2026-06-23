# `publish_wheel` の sdist 残し方が単一ジョブ依存・glob 依存で脆い問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-publish-wheel-sdist-fragile

## 目的

`.github/workflows/build.yml` の `publish_wheel` ジョブは、matrix で各プラットフォーム × Python バージョンの組み合わせを走らせる中で、`macos-15_arm64` × Python `3.12` のジョブだけが sdist (`*.tar.gz`) を `dist/` 配下に残す設計になっている。
他の matrix 組み合わせは `dist/*.tar.gz` をディレクトリ外へ退避し、sdist が PyPI publish の対象に入らないようにしている。
この設計は以下の脆さを抱えている。

1. 「sdist を残す責務」が `macos-15_arm64` × Python `3.12` の単一ジョブに集約されており、その 1 ジョブが何らかの理由 (一時的なランナー障害、SDK 側のビルド失敗など) で失敗すると、PyPI に sdist が一切 publish されない。wheel は他環境で成功している場合でも、sdist だけ欠落するリリースが出来上がる。
2. `[ -e dist/*.tar.gz ]` という bash の存在チェックが glob を直接 `[ -e ]` に渡しており、ファイルが複数あったり 0 個だったりすると `[ -e ]` の評価が不定 (実際は最初の 1 個だけ評価) になる。POSIX shell の `[ ]` は glob を取らないため、書き方として脆い。

本 issue では sdist の publish 経路を「単一 matrix ジョブの副作用」に依存させず、glob 評価も安全な形に整理することを目的とする。

## 優先度根拠

Medium とする。

- sdist が PyPI から欠落すると、wheel が無いプラットフォーム (例: Linux musl やまだサポートされていない CPython バージョン) のユーザーが pip install できなくなる。リリース時のユーザー影響は大きい。
- 一方、現状の構成は `macos-15_arm64` × Python `3.12` が大抵成功するという経験則で回っているため、即時障害ではない。リリース時に一度だけ問題化する経路であり、優先度は High ではなく Medium。

## 現状

`.github/workflows/build.yml` の 344-405 行付近 (`publish_wheel`):

```yaml
publish_wheel:
  if: contains(github.ref, 'tags/202')
  needs:
    - build_ubuntu
    - build_macos
    - build_windows
  strategy:
    fail-fast: false
    matrix:
      platform:
        - name: ubuntu-22.04_x86_64
        - name: ubuntu-22.04_armv8
        - name: macos-15_arm64
        - name: macos-14_arm64
        - name: windows-2025_x86_64
        - name: raspberry-pi-os_armv8
      python_version:
        - "3.12"
        - "3.13"
        - "3.14"
  runs-on: ubuntu-24.04
  ...
  steps:
    - uses: actions/download-artifact@...
      with:
        name: ${{ matrix.platform.name }}_python-${{ matrix.python_version }}
        path: dist
    - run: |
        if [ -e dist/*.tar.gz ]; then
          mv dist/*.tar.gz ./
        fi
    # matrix の中で１個だけソースディストリビューション用のデータを残しておく
    - run: mv *.tar.gz dist/
      if: ${{ matrix.platform.name == 'macos-15_arm64' && matrix.python_version == '3.12' }}
    ...
    - name: Publish package to PyPI
      uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0
```

脆さのポイント:

- sdist を含む `*.tar.gz` を残すのは `macos-15_arm64` && `3.12` の組み合わせだけ。
- `[ -e dist/*.tar.gz ]` は `[` (test) が glob を取らないため、ファイル数が 0 または 2 以上だと挙動が崩れる。0 個なら glob はそのまま `dist/*.tar.gz` というリテラルになり `-e` は偽。2 個以上なら最初のパス 1 つだけが評価対象になる (`[ -e a b ]` 相当でシンタックスエラーになる場合もある)。
- sdist は本来 1 つしか作られない想定だが、ファイル数の前提を bash の glob 評価に暗黙に依存させると将来の破綻リスクが残る。

## 設計方針

以下の組み合わせで再設計する。本 issue では断定しない。

1. sdist 専用ジョブを `publish_wheel` から分離する。
   - sdist は単一プラットフォームで 1 回だけ作って artifact にアップロードし、`publish_sdist` のような専用ジョブで publish する。
   - `publish_wheel` は wheel のみを取り扱う。matrix 内の "1 個だけ残す" 条件分岐を撤廃できる。
2. 存在チェックを堅牢にする。
   - `compgen -G "dist/*.tar.gz" > /dev/null` のような書き方で 0 / 1 / 多のいずれでも安全に判定する。
   - もしくは `shopt -s nullglob` を使い、`files=(dist/*.tar.gz); [ ${#files[@]} -gt 0 ]` のように配列で判定する。
3. PyPI の「同一バージョンの sdist は再 publish できない」制約も踏まえ、sdist publish 失敗時のリトライ方針を整理する (`skip-existing` 等の `gh-action-pypi-publish` オプションを使うかどうかを検討)。

最小変更案としては 1 + 2 の併用が妥当に見える。1 を行えば 2 のチェックロジック自体が不要になる経路もある。

## 完了条件

- sdist の publish が「単一の matrix 組み合わせの副作用」に依存しない構造になっていること (専用ジョブ化、もしくはそれに準ずる確実な経路で sdist がアップロードされる)。
- bash の glob を `[ -e ]` 直接に渡す書き方が解消されており、ファイル数 0 / 1 / 多のいずれでも安全に判定されること (専用ジョブ化でこのチェック自体が不要になる場合は、その旨を確認する)。
- リリース時に wheel と sdist が共に PyPI に揃って公開されること (実リリースもしくは TestPyPI で確認)。
- `publish_wheel` ジョブ全体の成功条件が、従来と同等以上に明瞭になっていること。
