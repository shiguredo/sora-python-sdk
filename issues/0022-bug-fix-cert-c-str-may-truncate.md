# 証明書を nb::bytes::c_str() で渡しており NUL バイトで切り詰められる可能性を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-cert-c-str-may-truncate

## 目的

`client_cert` / `client_key` / `ca_cert` を Sora C++ SDK の設定に渡す際、 `nb::bytes::c_str()` 経由で `const char*` を取得しているため、バイト列内に NUL バイト ( `\0` ) が含まれていると途中で切り詰められる。
PEM テキスト形式であれば NUL バイトを含まないため実用上は問題が顕在化しないが、 DER 形式のバイナリ証明書を渡された場合には不正なデータが SDK に渡り、 TLS ハンドシェイク失敗や不可解な接続エラーの原因となる。
バイト列を意図したまま忠実に伝搬させるよう修正する。

## 優先度根拠

Medium とする。

- PEM 形式での運用が一般的なため、現状の主要ユースケースでは顕在化していない。
- 一方で、 DER 形式の証明書を渡したいユーザーが現れた場合、エラーメッセージから原因を特定するのが極めて困難であり、サポートコストが大きい。
- 「バイト列の API としては明確に誤っている」構造的欠陥であり、低コストで修正できるため放置する理由がない。

## 現状

`src/sora.cpp` 191-198 行:

```cpp
if (client_cert) {
  config.client_cert = client_cert->c_str();
}
if (client_key) {
  config.client_key = client_key->c_str();
}
if (ca_cert) {
  config.ca_cert = ca_cert->c_str();
}
```

引数 `client_cert` / `client_key` / `ca_cert` は `std::optional<nb::bytes>` 型として受け取っており、 nanobind の `nb::bytes` は任意のバイナリ列を保持できる。
しかし、 `c_str()` で `const char*` を取得した上で `std::string` への暗黙変換が走ると、最初の NUL バイトで終端されたサブストリングとして扱われ、それ以降のバイトは捨てられる。
DER エンコードされた証明書は任意の位置に `\0` を含み得るため、この経路では破損する。
PEM 形式 (Base64 + ヘッダ/フッタのテキスト) は NUL を含まないため、現状のテスト・運用では問題が表面化していない。

## 設計方針

- `nb::bytes` のバイト列をサイズ込みで `std::string` に詰め直して `config.client_cert` 等に渡す。具体的には `std::string(client_cert->c_str(), client_cert->size())` を用いる。
- 同じパターンが 3 箇所 ( `client_cert` / `client_key` / `ca_cert` ) にあるため、それぞれ同様に修正する。
- 受け側 (`sora::SoraSignalingConfig`) の型がバイナリ列を正しく扱えるかを確認し、必要であれば API の整合性も確認する。

## 完了条件

- DER 形式のバイナリ証明書 (途中に NUL バイトを含むもの) を渡しても、切り詰められずに Sora C++ SDK に伝搬されることをコードレベルで確認できる。
- PEM 形式の証明書を用いた既存の接続テストが引き続き成功すること。
- `client_cert` / `client_key` / `ca_cert` の 3 経路すべてが同じ方針で修正されていること。
