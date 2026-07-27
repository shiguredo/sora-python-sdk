# SoraAudioSourceInterface の audio_observers_ がロックなしで複数スレッドから操作される問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Completed: 2026-07-27
- Model: Opus 4.7
- Branch: feature/fix-audio-observers-no-lock

## 目的

`SoraAudioSourceInterface` の `audio_observers_` は複数の経路 ( `SetVolume` / `RegisterAudioObserver` / `UnregisterAudioObserver` ) から読み書きされるにもかかわらず、専用のミューテックスで保護されていない。
同じクラス内の `sinks_` が `webrtc::MutexLock` で適切に保護されているのと対称性が崩れており、データレースおよびイテレーション中の変更による未定義動作の温床となる。
`audio_observers_` も同様にミューテックスで保護し、スレッド安全性を回復する。

## 優先度根拠

Medium とする。

- 現状はコールパターン上、登録・解除のタイミングが限定されており、観測可能なクラッシュには直結していない。
- ただし、 WebRTC のオーディオパスは複数の内部スレッド (デバイスバッファスレッド、シグナリングスレッド等) からアクセスされ得るため、現状のままでは見えないデータレースを抱えており、サニタイザ実行や free-threaded Python 環境で容易に問題が顕在化する。
- 同じクラス内の `sinks_` が正しく保護されている対照と比較して、 `audio_observers_` だけが裸である状況は構造的整合の崩れであり、低コストで修正できるため放置すべきでない。

## 現状

`src/sora_audio_source.cpp` 92-105 行:

```cpp
void SoraAudioSourceInterface::SetVolume(double volume) {
  for (auto* observer : audio_observers_) {
    observer->OnSetVolume(volume);
  }
}

void SoraAudioSourceInterface::RegisterAudioObserver(AudioObserver* observer) {
  audio_observers_.push_back(observer);
}

void SoraAudioSourceInterface::UnregisterAudioObserver(
    AudioObserver* observer) {
  audio_observers_.remove(observer);
}
```

対照的に、同ファイル 107-116 行の `sinks_` 側は `webrtc::MutexLock lock(&sink_lock_);` で保護されている:

```cpp
void SoraAudioSourceInterface::AddSink(webrtc::AudioTrackSinkInterface* sink) {
  webrtc::MutexLock lock(&sink_lock_);
  sinks_.push_back(sink);
}

void SoraAudioSourceInterface::RemoveSink(
    webrtc::AudioTrackSinkInterface* sink) {
  webrtc::MutexLock lock(&sink_lock_);
  sinks_.remove(sink);
}
```

`audio_observers_` 側のみロックを欠いており、 `SetVolume` がイテレーション中に `RegisterAudioObserver` / `UnregisterAudioObserver` が走るとイテレータが無効化される可能性がある。

## 設計方針

- `sink_lock_` と同様に、 `audio_observers_` 専用のミューテックス (例: `webrtc::Mutex observer_lock_;` ) を新設する。あるいは `sink_lock_` をそのまま流用してロックの粒度を統一する選択肢もあるが、ロック保持中に呼ばれる `observer->OnSetVolume(volume)` がさらに WebRTC 側のロックを取る可能性があるため、ロックの順序とデッドロックリスクを慎重に確認する。
- `SetVolume` の中で observer を呼ぶ前に、ロック下で `audio_observers_` のスナップショットをコピーし、ロックを外してからコピー上で `OnSetVolume` を呼ぶ実装も有効。これにより observer 側コールバックでさらに `Register` / `Unregister` が呼ばれてもデッドロックしない。
- どちらの方針を取るかは、 observer コールバックの中で `audio_observers_` を変更し得るかどうかを確認したうえで決める。

## 完了条件

- `audio_observers_` の読み書き ( `SetVolume` / `RegisterAudioObserver` / `UnregisterAudioObserver` ) が、明示的なミューテックスで保護されること。
- `sinks_` と `audio_observers_` の保護方針が対称になり、片方だけがロックされる構造的不整合が解消されること。
- observer コールバック中の再エントリでデッドロックしないことが、実装または明示的なテスト/コメントで確認できる。
- 既存テストが回帰しないこと。

## 解決方法

`observer_lock_` (`webrtc::Mutex`) を追加し、`RegisterAudioObserver` / `UnregisterAudioObserver` をロック下で操作するようにした。

`SetVolume` はロック下で `audio_observers_` のスナップショットをコピーし、ロックを外してから `OnSetVolume` を呼ぶ。
コールバック中に Register / Unregister が再入してもデッドロックしない。
