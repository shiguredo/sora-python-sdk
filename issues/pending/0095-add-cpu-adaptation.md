# CPU アダプテーションの有効/無効を create_connection で指定できるようにする

- Created: 2026-09-11
- Completed: -
- Branch: feature/add-cpu-adaptation
- Polished: -
- Reporter: @voluntas

## 目的

libwebrtc の CPU アダプテーション (CPU overuse detection) の有効/無効を Python SDK から切り替えられるようにする。CPU 負荷が高い環境で解像度やフレームレートがどう制御されるかを Python SDK のテストで検証できるようにする。

## 現状

- `Sora.create_connection()` には CPU アダプテーションを指定する引数が無い。
  - `src/sora.h` の `Sora::CreateConnection` のシグネチャに無い。
  - `src/sora.cpp` の `Sora::CreateConnection` で `sora::SoraSignalingConfig` に設定していない。
  - `src/sora_sdk_ext.cpp` の `Sora` クラスの `create_connection` バインディングに無い。
  - `src/sora_sdk/sora_sdk_ext.pyi` の `create_connection` の型スタブに無い。
- デグレード設定 (`degradation_preference` / `SoraDegradationPreference`) は既に公開されている。これは CPU アダプテーションや帯域制約が働くときに解像度とフレームレートのどちらを優先するかを指定する別設定であり、CPU アダプテーション自体の有効/無効は指定できない。
- Sora C++ SDK の `SoraSignalingConfig` には `std::optional<bool> cpu_adaptation` があり、`src/sora_signaling.cpp` で `rtc_config.set_cpu_adaptation()` に反映される。未指定の場合は従来どおり macOS のサイマルキャスト時のみ自動的に無効化される。
- Python SDK が利用する Sora C++ SDK (`DEPS` の `SORA_CPP_SDK_VERSION`) には既に `cpu_adaptation` が含まれており、上流側の追加対応は不要。
- libwebrtc では `RTCConfiguration::set_cpu_adaptation()` が `media_config.video.enable_cpu_adaptation` を設定する。これは PeerConnection constraint `googCpuOveruseDetection` に対応する。
- CPU アダプテーションを検証するテストは `tests/` に無い。`tests/test_degradation_preference.py` は劣化時の優先度だけを確認している。

## 設計方針

保留を解除したら、次の方針で追加する。

- `Sora.create_connection()` に `cpu_adaptation: Optional[bool] = None` を追加する。
- 未指定 (`None`) の場合は C++ SDK のデフォルト (macOS のサイマルキャスト時のみ自動無効化) に委ねる。`degradation_preference` と同じ扱いにする。
- 値をそのまま `SoraSignalingConfig::cpu_adaptation` に渡す。
- 実装箇所は `src/sora.h` / `src/sora.cpp` / `src/sora_sdk_ext.cpp` / `src/sora_sdk/sora_sdk_ext.pyi`。
- `tests/client.py` に `cpu_adaptation` 引数を追加し、必要に応じて CPU アダプテーションの有無で挙動が変わることを確認するテストを追加する。CPU 負荷依存のため CI で安定して検証できるかは要確認。

## 完了条件

- `Sora.create_connection(..., cpu_adaptation=True)` / `cpu_adaptation=False` が受け付けられ、C++ SDK の `SoraSignalingConfig::cpu_adaptation` に渡る。
- 未指定時は C++ SDK のデフォルト挙動が維持される。
- `src/sora_sdk/sora_sdk_ext.pyi` の型スタブが更新されている。
- `CHANGES.md` に `[ADD]` エントリが追加されている。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- 元になった報告に本文が無く、追加の目的、想定ユースケース、デフォルト挙動、テスト方針が明文化されていない。
- `cpu_adaptation` を `create_connection` の引数として公開するか、`Sora` のコンストラクター側に置くかの設計判断が必要である (`degradation_preference` と揃えるのが自然という推測はある)。
- CPU アダプテーションは CPU 負荷に依存する挙動のため、CI で安定して検証できるテストを作れるか未確認。
- 引数名を `cpu_adaptation` とするかを含め、命名の合意が必要。

再開するときは reopened にしてから実装を進める。
