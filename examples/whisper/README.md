# whispercpp のインストール

## 注意

macOS 13.x の Apple Silicon でのみ動作を確認しています。

## セットアップ

https://pypi.org/project/whispercpp/

```console
$ pip install whispercpp
```

これだけで実行可能になっているはず。
実行できなかった場合は、下記のようにソースからビルドしてインストールする。

## エラーとその対処

### `GLIBCXX_3.4.29` not found

libstdc++6 が古い可能性があるためアップデートを行う。

```console
$ sudo apt update libstdc++6
```

下記のコマンドを実行し確認する。

```console
$ strings /lib/x86_64-linux-gnu/libstdc++.so.6 | grep GLIBCXX_3.4.29
```

出力がある場合は実行可能になっている。
出力がない場合は次を確認する。

### `GLIBCXX_3.4.29` がインストールされない場合

#### ビルドを行った Python のバージョンと一致しないと表示され実行できない場合

pip で配布されているものをそのまま実行することはできない。
pip でインストールされているものを削除する。

```
$ pip uninstall whispercpp
``` 

ソースからビルドしてインストールする

```console
$ pip install git+https://github.com/aarnphm/whispercpp.git@v0.0.17 -vv
```

#### `f'spec_for_{name}'` で SyntaxError: invalid syntax というエラーがでる

python が python2.7 を見に行っている場合に生じる。
再度ソースからビルドしてのインストールを試す。

```console
$ sudo apt install python-is-python3
```
