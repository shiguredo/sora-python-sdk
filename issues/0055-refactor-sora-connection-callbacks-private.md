# `SoraConnection` のコールバック群を public のまま外部に晒している状態を private に閉じる

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/sora-connection-callbacks-private

## 目的

`SoraConnection` クラスでは Python 側からコールバックを設定するために `on_set_offer_` / `on_disconnect_` / `on_notify_` / `on_push_` / `on_message_` / `on_rpc_` / `on_switched_` / `on_track_` / `on_data_channel_` などのメンバ変数群がクラス本体の `public:` セクションに直接置かれている。nanobind の `def_rw` でこのメンバを外向けに公開しているためだが、結果として「C++ 側から見た内部状態」と「Python 側に公開している API 表面」が等しくなってしまい、C++ 内部のリファクタリングが Python 側の API 互換を必ず巻き込む状態になっている。

`SoraAudioSinkImpl` も同様に `on_data_` / `on_format_` が public で公開されているが、これらはコメント上「廃止予定」と明示されている。廃止予定であることをマシン可読な形 (deprecation 属性) で伝える経路が無く、CHANGES.md にも除去スケジュールが無い。

このまま放置すると、内部実装の進化と外向け API の互換維持が分離できず、廃止予定の API もユーザーに気付かれないまま使われ続ける。public 露出と internal 実装を分離し、廃止予定は明示的なスケジュールを付けたうえで除去する。

## 優先度根拠

Medium とする。

- 動作上のバグではないため High ではない。
- ただし「C++ 内部のメンバを直接 public で晒している」状態は API 進化を強く阻害する。例えば「コールバックの引数を増やしたい」「コールバック登録時の前提条件を変えたい」と思った瞬間、Python ABI 互換を考慮しないと触れない。今のうちに accessor 経由に切り替えておくと、後から弁明的な互換レイヤを足す必要が減る。
- `on_data_` / `on_format_` の「廃止予定」も、明示的に `[[deprecated]]` を付けて CHANGES.md にスケジュールを切れば、利用者側が次のメジャーで除去されることを把握できる。今のコメントだけの宣言は実効性が低い。
- 修正は機械的だが範囲が C++ クラス本体 + nanobind バインディング + CHANGES.md にまたがるため、Low では片付かない。

## 現状

### `SoraConnection` のコールバック群が public

`src/sora_connection.h:144-156`:

```cpp
// sora::SoraSignalingObserver のコールバック関数が呼び出された時に対応して呼び出す Python の関数を保持する
std::function<
    void(sora::SoraSignalingType, sora::SoraSignalingDirection, std::string)>
    on_signaling_message_;
std::function<void(std::string)> on_set_offer_;
std::function<void(int, std::string)> on_ws_close_;
std::function<void(sora::SoraSignalingErrorCode, std::string)> on_disconnect_;
std::function<void(std::string)> on_notify_;
std::function<void(std::string)> on_push_;
std::function<void(std::string, nb::bytes)> on_message_;
std::function<void(nb::bytes)> on_rpc_;
std::function<void(std::string)> on_switched_;
std::function<void(nb::ref<SoraMediaTrack>)> on_track_;
std::function<void(std::string)> on_data_channel_;
```

すべてクラスの `public:` 領域に置かれ、nanobind の `def_rw` で Python から直接代入される。

### `SoraAudioSinkImpl` の廃止予定コールバック

`src/sora_audio_sink.h:66-72`:

```cpp
/**
 * 実装上の留意点：コールバックと Read 関数の共存はパフォーマンスや使い方の面で難しいことが判明したので、
 * on_data_, on_format_ ともに廃止予定です。
*/
std::function<void(nb::ndarray<nb::numpy, int16_t, nb::shape<-1, -1>>)>
    on_data_;
std::function<void(int, size_t)> on_format_;
```

「廃止予定」とコメントには書いてあるが、`[[deprecated]]` 等のマーカーは無い。Python から見ても廃止予定であることが API ドキュメント・型ヒント・実行時警告のいずれにも現れていない。

## 設計方針

C++ 内部メンバと Python 公開 API を分離する。

1. `on_*` の `std::function` メンバを `private:` または `protected:` に移し、外部からは setter / accessor 経由でのみ書き込めるようにする。nanobind 側は `def_prop_rw` / `def("set_on_xxx", ...)` 等で受ける。互換維持のため、現状の Python 表面 (`connection.on_track = callable` のようなプロパティ代入) は当面そのままにできる経路を検討する。
2. `SoraAudioSinkImpl::on_data_` / `on_format_` には `[[deprecated("Use Read() instead. Will be removed in <release>.")]]` を付ける。Python 側に向けた deprecation 通知方法 (FutureWarning 等) も検討する。
3. CHANGES.md に「`SoraAudioSinkImpl::on_data_` / `on_format_` は `<対象リリース>` で除去予定」を明記し、移行先 (`Read()` 系 API) を案内する。
4. `SoraConnection` の `on_*` のうち、今後仕様変更したいもの (例: 引数を増やす) があれば、まず private 化して accessor 経由のシグネチャを定義してから変更する。

短期では「private 化 + accessor で再公開」までを行い、`on_data_` / `on_format_` の除去は次メジャーで実施する。

## 完了条件

- `SoraConnection::on_*` メンバが `private:` または `protected:` に置かれ、外部からは accessor 経由でのみ設定できる構造になっていること。
- Python 側からの設定方法 (例: `connection.on_track = callable`) について、互換を維持する場合と互換を切る場合のいずれかが選択され、選択結果が CHANGES.md に記載されていること。
- `SoraAudioSinkImpl::on_data_` / `on_format_` に `[[deprecated]]` 属性または同等のマーカーが付いていること。
- CHANGES.md に廃止予定 API の対象リリースと移行先が明記されていること。
- 既存テストが通ること。
