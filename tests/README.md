# examples の E2E テスト

## 環境変数

- `TEST_SIGNALING_URLS`
- `TEST_CHANNEL_ID_PREFIX`
- `TEST_SECRET_KEY`
- `OPENH264_PATH`
  - OpenH264 のバイナリの **絶対** パスを指定してください
- `TEST_LIBWEBRTC_LOG`
  - デフォルトは `none` です
  - `none`, `verbose`, `info`, `warning`, `error` のいずれかを指定してください

## 簡易 CLI 実行

`tests/cli.py` で `SoraClient` を手軽に実行できます。

### Blend2D で 120fps・解像度 960x540・厳密ペーシング

```bash
uv run tests/cli.py --role sendonly --video --fake-video \
  --fake-video-type blend2d --video-codec-type VP9 \
  --video-width 960 --video-height 540 --framerate 120 --precise-timing
```

### 備考

- `--duration` を省略すると無制限で動作します（Ctrl-C で終了）。
- フレームレートは `--framerate`（または `--fps`）で指定できます
  - 未指定は 30 fps
- 解像度は `--video-width`/`--video-height` で指定
  - デフォルト 960x540
- フレームペーシングをより厳密にするには `--precise-timing` を付与
  - CPU 使用率が上がります
