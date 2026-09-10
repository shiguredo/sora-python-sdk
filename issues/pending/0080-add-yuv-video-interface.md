# 映像データを YUV 形式でやり取りする口を追加する

- Created: 2026-09-11
- Completed: -
- Branch: feature/add-yuv-video-interface
- Polished: -
- Reporter: @sile

## 目的

映像データの送受信で YUV (I420) を直接扱えるようにし、RGB を経由する不要な変換をなくす。

映像処理ライブラリと連携する際、ライブラリ側で YUV から RGB への変換が走り、その後に SDK 側で RGB から YUV への変換が走る、という指摘がある (受信時は逆方向の変換が同様に発生する)。YUV のまま受け渡しできれば、変換にかかる CPU コストと変換による画素値の劣化を削減できる。

## 現状

受信側:

- `src/sora_video_sink.h` の `SoraVideoSinkImpl` が `on_frame_` コールバックで `SoraVideoFrame` を渡す。
- `src/sora_video_sink.cpp` の `SoraVideoFrame` コンストラクタが `libyuv::ConvertFromI420` で I420 から BGR (FOURCC_24BG) に変換し、`SoraVideoFrame::Data()` が H x W x 3 の `uint8` ndarray として返す。変換はフレーム到着時に 1 回だけ行われる。
- BGR 以外の形式で受け取る口がないため、YUV のまま使いたい利用者も BGR への変換コストを必ず払う。

送信側:

- `src/sora_video_source.h` の `SoraVideoSource::OnCaptured` が H x W x 3 の BGR ndarray のみを受け取る。
- `src/sora_video_source.cpp` の `SoraVideoSource::SendFrame` が `libyuv::ConvertToI420` で BGR から I420 に変換してから `sora::ScalableVideoTrackSource::OnCapturedFrame` に渡す。
- I420 のフレームをそのまま送る口がないため、YUV を生成するライブラリの出力を一度 BGR に変換してから渡す必要がある。

バインディングとラッパー:

- `src/sora_sdk_ext.cpp` で `SoraVideoSource::on_captured` は H x W x 3 の ndarray 固定で、`SoraVideoFrame::data` と `SoraVideoSinkImpl::on_frame` が公開されている。
- Python 側のラッパーは `src/sora_sdk/__init__.py` の `SoraVideoSink`。

## 設計方針

保留を解除したら、まず利用側が扱う YUV の形式とメモリ配置を確認し、次の点を決める。

受信側:

- `SoraVideoFrame` に I420 のまま返すアクセサを追加する。Y / U / V を個別の ndarray で返す形や、I420 の連続バッファとして返す形が考えられる。
- あるいは `SoraVideoSink` の生成時に欲しい形式 (BGR / I420) を指定できるようにし、不要な変換を行わない。この場合は BGR を既定値にして後方互換を保つ。

送信側:

- `SoraVideoSource::OnCaptured` に I420 を受け取るオーバーロードを追加する。Y / U / V を個別の ndarray で受け取る形や、I420 のバッファとストライドを受け取る形が考えられる。
- nanobind の ndarray は shape を型で固定するため、複数の形式をどうバインドするかは実装時に検討する。

共通:

- 既存の BGR API は残し、破壊的変更にしない。
- 変換の有無を利用者が明示できる API とし、形式の自動判別は行わない。

## 完了条件

- 受信した映像を YUV (I420) のまま取得できる。
- YUV (I420) のフレームを BGR を経由せずに送信できる。
- BGR への変換が行われないことを確認できるテストが `tests/` にある。
- 利用方法が README または docstring に記載されている。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- 利用側が扱う YUV の形式 (I420 固定か、NV12 なども必要なのか) とメモリ配置を確認する必要がある。
- 変換をどの層で扱うか (`SoraVideoSink` / `SoraVideoSource` のオプションにするか、フレームのアクセサを追加するか) を決める必要がある。
- nanobind の ndarray は shape をコンパイル時に固定するため、I420 のバインド方法が未確定。
- 実際の利用シーンでどの程度の削減効果が見込めるかの確認が必要。

再開するときは reopened にしてから実装を進める。
