# Sora C++ SDK の worker_thread 削除に追随する

- Created: 2026-09-15
- Completed: -
- Branch: feature/update-follow-worker-thread-removal
- Polished: -

## 目的

libwebrtc の issue 558821261「Deprecate and remove PeerConnectionFactoryDependencies::worker_thread」で worker thread が廃止される。CL 501620「Default worker thread to network thread」と CL 502480「Warn when a distinct worker thread is configured」はマージ済みで、削除系の CL 499302 / 501640 / 501720 / 502000 / 502500 / 502860 / 502940 / 502960 はレビュー中である。`PeerConnectionFactoryDependencies::worker_thread` と `PeerConnectionFactoryInterface::worker_thread()` は将来削除される。

対応は 2 段階に分ける。

- 方針 1 (いますぐ実施): 専用の worker thread をやめて network thread を使う
- 方針 2 (558821261 を実装した libwebrtc をマージした後に実施): worker_thread の利用箇所と API を全て無くす

本リポジトリは worker thread を独自生成しておらず、sora-cpp-sdk の `SoraClientContext` が作った `PeerConnectionFactoryDependencies` を `configure_dependencies` コールバックで借りて `dependencies.worker_thread` を参照しているだけである。したがって方針 2 が該当する。方針 1 の時点では sora-cpp-sdk が `dependencies.worker_thread` に network thread を渡すため、本リポジトリは変更不要で、方針 2 まで遅延できる。

## 現状

- `src/sora_factory.cpp` の `SoraFactory` コンストラクタで `context_config.configure_dependencies` に設定するラムダ内の 1 箇所だけが `dependencies.worker_thread` を使っている。`dependencies.audio_mixer = dependencies.worker_thread->BlockingCall([&env]() { return DummyAudioMixer::Create(env); });` で、`DummyAudioMixer` を独自に差し込んでいる。
- `DummyAudioMixer` は `webrtc::Environment` と自前の `TaskQueue` だけで完結し、worker thread に依存しない (`src/dummy_audio_mixer.cpp`)。
- `context_config.use_audio_device` は false に固定しており、通常の AudioMixer を使うと `use_audio_device` が false のとき音声のループが全て止まってしまうため、自前の AudioMixer を設定している (`src/sora_factory.cpp` のコメント)。
- `dependencies` は sora-cpp-sdk の `SoraClientContextConfig::configure_dependencies` 経由で受け取っており、自前で `PeerConnectionFactoryDependencies` を構築していない。独自の worker thread も生成していない。
- 依存は `DEPS` の `SORA_CPP_SDK_VERSION=2026.3.0-canary.6` / `WEBRTC_BUILD_VERSION=m154.8037.1.1`。

## 設計方針

- 前提条件: sora-cpp-sdk の worker_thread 削除がリリースされ、`SORA_CPP_SDK_VERSION` を更新できる状態になっていること。現時点では存在しないため、本 issue には着手できない。
- `dependencies.worker_thread` を `dependencies.network_thread` に置き換える (sora-cpp-sdk 側で network thread が worker thread として使われるようになるため)。
- `DEPS` の `SORA_CPP_SDK_VERSION` を更新する。

## 完了条件

- `worker_thread` の参照が 0 件であること。
- `use_audio_device = false` でも音声が動作すること。
- `CHANGES.md` の `## develop` にエントリが追記されていること。
