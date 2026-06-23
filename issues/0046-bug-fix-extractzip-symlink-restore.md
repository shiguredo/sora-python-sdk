# `_extractzip` の symlink 復元処理が展開順序に依存して壊れる経路を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-extractzip-symlink-restore

## 目的

`buildbase.py` の `_extractzip` は zip 内に含まれる symlink エントリを復元するために、`extractall` 後に対象ファイルを読み取り、`os.remove` してから `os.symlink` で symlink を作り直している。
ところがこの再作成は「symlink の指す先 (`src`) が既に存在する場合のみ」行う条件分岐 (`if os.path.exists(src):`) になっており、symlink エントリが「まだ展開されていないファイル」を指している場合に symlink が作られず、`os.remove` でファイルだけが消える状態になる。
`extractall` の展開順は zip の内部順序に依存するため、エントリの並び次第で「symlink を復元できないまま実体ファイルだけが消える」破壊的な結果になりうる。
この順序依存の壊れ方を解消し、symlink の復元を確実に行うことを目的とする。

## 優先度根拠

Medium とする。

- ビルドスクリプトの依存物展開 (`webrtc.zip` / `sora.zip` など) で利用されており、失敗するとビルドが進まないだけでなく、`os.remove` で実体が消えた状態で symlink も無いという中途半端な状態が残る。再現条件次第で「ビルド成果物が黙って壊れる」可能性があるため放置できない。
- 一方、現在配布している zip は内容物の順序が安定しており、現状では再現していないと見られる。生成側 zip の構造が変わると突然壊れる潜在バグであり、優先度は High ではなく Medium。

## 現状

`buildbase.py` の 308-329 行:

```python
# 解凍した上でファイル属性を付与する
def _extractzip(z: zipfile.ZipFile, path: str):
    z.extractall(path)
    if platform.system() == "Windows":
        return
    for info in z.infolist():
        if info.is_dir():
            continue
        filepath = os.path.join(path, info.filename)
        mod = info.external_attr >> 16
        if (mod & 0o120000) == 0o120000:
            # シンボリックリンク
            with open(filepath, encoding="utf-8") as f:
                src = f.read()
            os.remove(filepath)
            with cd(os.path.dirname(filepath)):
                if os.path.exists(src):
                    os.symlink(src, filepath)
        if os.path.exists(filepath):
            # 普通のファイル
            os.chmod(filepath, mod & 0o777)
```

問題は次の構造にある。

1. `z.extractall(path)` で全エントリを通常ファイルとして展開する。symlink エントリは「リンク先文字列をテキストとして書き出したファイル」になる。
2. その後 `infolist()` を走査し、ファイルモードが symlink (`0o120000`) のエントリについてのみ、リンク先文字列を読み取り、ファイルを削除して `os.symlink` で symlink を作り直す。
3. ところが `os.symlink(src, filepath)` を呼ぶ前に `if os.path.exists(src):` で「リンク先が既に存在するか」を確認している。POSIX の symlink は dangling でも作れるため、この条件は本来不要。
4. zip 内のエントリ順序によっては、symlink を作り直そうとした時点でリンク先がまだ別のエントリとして書かれているとは限らないし、相対パスで他のディレクトリを指すこともある。`os.path.exists(src)` が偽になると、symlink は作られず、しかも `os.remove(filepath)` は実行済みなのでファイルだけが消える。

結果として、zip の中身が「対象ファイル → symlink エントリ」の順に並んでいれば偶然動くが、順序が変わると symlink が復元できないまま壊れる、という展開順序依存のバグになっている。
さらに `with open(filepath, encoding="utf-8") as f:` で UTF-8 デコードしているため、リンク先文字列が UTF-8 でないと例外で死ぬ可能性もある (副次的な問題)。

## 設計方針

順序依存を取り除くために以下のいずれかを採用する。本 issue では断定しない。

1. `os.path.exists(src)` チェックを撤廃する。POSIX の symlink は dangling でも作成可能であり、ターゲットファイルの存在確認は不要。zip 内に symlink ターゲットが含まれていれば、最終的に解決される。
2. 走査を 2 パスに分ける。第 1 パスで全エントリを通常ファイルとして展開、第 2 パスで symlink エントリだけを処理する。第 1 パス完了時には全実体が揃っているため `os.path.exists(src)` チェックは事実上常に真になる (が、結局このチェック自体は不要)。
3. 上記いずれの場合も、`os.remove` で実体を消した後に `os.symlink` 作成が失敗した場合のロールバック方針を決める (例外時に展開先ディレクトリごと削除するなど) ことで、半壊状態が残らないようにする。

最小変更案としては「`if os.path.exists(src):` の条件を外して unconditional に `os.symlink(src, filepath)` を呼ぶ」が妥当に見える。
あわせて、symlink 内容のデコード時の `encoding="utf-8"` についても、Python の `os.readlink` 等の挙動と整合する形で見直すことを検討する。

## 完了条件

- zip 内エントリ順序がどのような並びでも、symlink エントリが正しく symlink として復元されること。
- symlink 復元処理中に失敗した場合、実体ファイルだけが消えた半壊状態が残らないこと (例外を上に投げる、もしくは展開ディレクトリを破棄する)。
- Windows 環境では現状どおり何もしないこと (`platform.system() == "Windows"` の早期 return を維持)。
- 既存の `_extractzip` 呼び出し元 (依存物展開) が引き続き正常に動作すること。
