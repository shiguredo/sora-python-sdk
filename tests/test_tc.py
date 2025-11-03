"""tc egress を使用した帯域制限のテスト。

このテストは pyroute2 を使用して Linux の tc (traffic control) により
ローカルインターフェースの egress (送信方向) に帯域制限を適用し、
TURN 経由での接続に対する効果を検証する。
"""

import os
import sys
import time
from typing import Optional

import pytest
from client import SoraClient, SoraRole

# TC=1 環境変数が設定されており、かつ Linux 環境の場合のみテストを実行
pytestmark = pytest.mark.skipif(
    os.getenv("TC") != "1" or sys.platform != "linux",
    reason="TC=1 環境変数と Linux 環境が必要",
)

# pyroute2 がインストールされていない場合はスキップ
pyroute2 = pytest.importorskip("pyroute2")

# テスト用の設定値
INITIAL_BITRATE_KBPS = 1200  # 初期ビットレート (kbps)
BANDWIDTH_LIMIT_KBPS = 250  # 帯域制限値 (kbps)
MIN_BITRATE_BEFORE_LIMIT_KBPS = 500  # 制限前の最小ビットレート (kbps)


def get_default_interface() -> str:
    """デフォルトのネットワークインターフェース名を取得する。

    Returns:
        デフォルトルートで使用されているインターフェース名
    """
    try:
        with pyroute2.IPRoute() as ipr:
            # デフォルトルートを取得（IPv4）
            for route in ipr.get_routes(family=2):  # AF_INET = 2
                # dst が存在しない場合がデフォルトルート
                if not route.get_attr("RTA_DST"):
                    oif = route.get_attr("RTA_OIF")
                    if oif:
                        # インターフェース情報を取得
                        links = ipr.get_links(oif)
                        if links:
                            ifname = links[0].get_attr("IFLA_IFNAME")
                            return ifname
    except Exception as e:
        print(f"デフォルトインターフェースの取得に失敗: {e}")

    # フォールバックとして eth0 を返す
    return "eth0"


class TCEgressManager:
    """tc netem qdisc を使用して egress (送信方向) のネットワーク帯域制限を管理する。"""

    def __init__(self, interface: str = "eth0") -> None:
        """
        TC egress 帯域制限マネージャーを初期化する。

        Args:
            interface: tc ルールを適用するネットワークインターフェース
        """
        self.interface: str = interface
        self._bandwidth_applied: bool = False
        self.ipr: Optional["pyroute2.IPRoute"] = None

    def __enter__(self):
        """コンテキストマネージャーのエントリ。"""
        self.ipr = pyroute2.IPRoute()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了 - tc ルールをクリーンアップする。"""
        try:
            self.cleanup()
        finally:
            if self.ipr:
                self.ipr.close()

    def add_bandwidth_limit(self, rate_kbps: int) -> None:
        """
        インターフェースの egress に帯域制限を追加する。

        Args:
            rate_kbps: 帯域制限 (Kbps)

        Raises:
            IndexError: インターフェースが見つからない場合
            Exception: tc 操作が失敗した場合
        """
        if not self.ipr:
            raise RuntimeError("IPRoute が初期化されていません")

        # インターフェースインデックスを取得する
        indices = self.ipr.link_lookup(ifname=self.interface)
        if not indices:
            raise IndexError(f"インターフェース '{self.interface}' が見つかりません")
        idx = indices[0]

        # tbf (Token Bucket Filter) qdisc で帯域制限を追加する
        # root=True を指定すると handle は自動的に 0x10000 (= "1:") に設定される
        # rate: 帯域制限 (文字列で "750 kbit" のように指定)
        # burst: バーストサイズ (bytes)
        # latency: 最大遅延時間 (文字列で "50ms" のように指定)
        self.ipr.tc(
            "add",
            "tbf",
            idx,
            root=True,
            rate=f"{rate_kbps}kbit",
            # 32KB
            burst=32768,
            latency="50ms",
        )
        self._bandwidth_applied = True
        print(f"tc egress 帯域制限を追加: interface={self.interface}, rate={rate_kbps}kbps")

    def add_delay(self, delay_ms: int) -> None:
        """
        インターフェースの egress に遅延を追加する。

        Args:
            delay_ms: 遅延 (ミリ秒)

        Raises:
            IndexError: インターフェースが見つからない場合
            Exception: tc 操作が失敗した場合
        """
        if not self.ipr:
            raise RuntimeError("IPRoute が初期化されていません")

        # インターフェースインデックスを取得する
        indices = self.ipr.link_lookup(ifname=self.interface)
        if not indices:
            raise IndexError(f"インターフェース '{self.interface}' が見つかりません")
        idx = indices[0]

        # netem qdisc で遅延を設定
        self.ipr.tc(
            "add",
            "netem",
            idx,
            root=True,
            delay=delay_ms * 1000,  # マイクロ秒に変換
        )
        self._bandwidth_applied = True
        print(f"tc egress 遅延を追加: interface={self.interface}, delay={delay_ms}ms")

    def get_stats(self) -> dict:
        """tc qdisc の統計情報を取得する。

        Returns:
            統計情報を含む辞書 (sent_bytes, sent_packets, drops など)
        """
        if not self.ipr:
            raise RuntimeError("IPRoute が初期化されていません")

        # インターフェースインデックスを取得する
        indices = self.ipr.link_lookup(ifname=self.interface)
        if not indices:
            raise IndexError(f"インターフェース '{self.interface}' が見つかりません")
        idx = indices[0]

        # tc qdisc の情報を取得する
        for qdisc in self.ipr.get_qdiscs(idx):
            # netem qdisc の統計情報を抽出する
            if qdisc.get_attr("TCA_OPTIONS"):
                stats = {
                    "sent_bytes": qdisc.get("bytes", 0),
                    "sent_packets": qdisc.get("packets", 0),
                    "drops": qdisc.get("drops", 0),
                    "overlimits": qdisc.get("overlimits", 0),
                    "requeues": qdisc.get("requeues", 0),
                }
                return stats

        return {}

    def cleanup(self) -> None:
        """インターフェースから tc 帯域制限設定を削除する。"""
        if not self._bandwidth_applied:
            return

        if not self.ipr:
            return

        try:
            indices = self.ipr.link_lookup(ifname=self.interface)
            if not indices:
                return
            idx = indices[0]
            # qdisc を削除する
            # 削除時には kind を指定せず、index と root のみを指定する
            self.ipr.tc("del", index=idx, root=True)
            self._bandwidth_applied = False
            print(f"tc egress 帯域制限を削除: interface={self.interface}")
        except Exception as e:
            # クリーンアップ時のエラーは無視する (qdisc が存在しない可能性がある)
            print(f"tc egress 帯域制限の削除時にエラー (無視): {e}")


def verify_tc_settings(interface: str, qdisc_type: str = "tbf") -> bool:
    """tc の設定が存在するか確認する。

    Args:
        interface: ネットワークインターフェース名
        qdisc_type: 確認する qdisc の種類 (tbf または netem)

    Returns:
        設定が存在する場合は True
    """
    try:
        with pyroute2.IPRoute() as ipr:
            # インターフェースインデックスを取得
            indices = ipr.link_lookup(ifname=interface)
            if not indices:
                return False
            idx = indices[0]

            # qdisc の情報を取得
            for qdisc in ipr.get_qdiscs(idx):
                kind = qdisc.get_attr("TCA_KIND")
                if kind == qdisc_type:
                    return True
        return False
    except Exception as e:
        print(f"tc 設定の確認に失敗: {e}")
        return False


def show_tc_stats(interface: str) -> None:
    """tc の統計情報を表示する。

    Args:
        interface: ネットワークインターフェース名
    """
    try:
        with pyroute2.IPRoute() as ipr:
            # インターフェースインデックスを取得
            indices = ipr.link_lookup(ifname=interface)
            if not indices:
                print(f"インターフェース {interface} が見つかりません")
                return
            idx = indices[0]

            # qdisc の情報を取得して表示
            print(f"\ntc 統計情報 ({interface}):")
            for qdisc in ipr.get_qdiscs(idx):
                kind = qdisc.get_attr("TCA_KIND")
                handle = qdisc.get("handle", 0)
                parent = qdisc.get("parent", 0)

                # 統計情報
                sent_bytes = qdisc.get("bytes", 0)
                sent_packets = qdisc.get("packets", 0)
                drops = qdisc.get("drops", 0)
                overlimits = qdisc.get("overlimits", 0)

                print(f"  qdisc {kind} handle {handle:#x} parent {parent:#x}")
                print(f"    Sent {sent_bytes} bytes {sent_packets} packets")
                print(f"    drops {drops}, overlimits {overlimits}")
    except Exception as e:
        print(f"tc 統計情報の取得に失敗: {e}")


def show_webrtc_stats(stats: list) -> None:
    """WebRTC の統計情報を表示する。

    Args:
        stats: get_stats() で取得した統計情報のリスト
    """
    try:
        print("\nWebRTC 統計情報:")
        for stat in stats:
            if stat.get("type") == "outbound-rtp":
                rid = stat.get("rid", "")
                rid_label = f" (rid={rid})" if rid else ""
                print(f"  outbound-rtp{rid_label}:")
                print(f"    ssrc: {stat.get('ssrc')}")
                print(f"    kind: {stat.get('kind')}")
                if rid:
                    print(f"    rid: {rid}")
                print(f"    bytesSent: {stat.get('bytesSent')}")
                print(f"    packetsSent: {stat.get('packetsSent')}")
                if "targetBitrate" in stat:
                    print(f"    targetBitrate: {stat.get('targetBitrate')} bps")
                if "totalPacketSendDelay" in stat:
                    print(f"    totalPacketSendDelay: {stat.get('totalPacketSendDelay')} s")
    except Exception as e:
        print(f"WebRTC 統計情報の表示に失敗: {e}")


def test_tc_egress_bandwidth_limit(settings):
    """TURN ポート取得後に tc egress で帯域制限をかける。"""
    print("\n" + "=" * 60)
    print(f"テスト: tc egress 帯域制限 ({BANDWIDTH_LIMIT_KBPS}kbps) の適用")
    print("=" * 60)

    interface = get_default_interface()
    print(f"使用するネットワークインターフェース: {interface}")

    with SoraClient(
        settings,
        SoraRole.SENDONLY,
        simulcast=True,
        audio=False,
        video=True,
        video_codec_type="VP8",
        video_bit_rate=INITIAL_BITRATE_KBPS,
        video_width=960,
        video_height=540,
    ) as sendonly:
        time.sleep(10)

        # offer_message が受信されていることを確認
        assert sendonly.offer_message is not None

        # turn_ports プロパティから TURN ポートを取得
        turn_ports = sendonly.turn_ports

        # UDP ポートが取得できていることを確認
        assert len(turn_ports["udp"]) > 0, "UDP ポートが取得できていません"

        # 最初の UDP ポートを使用
        udp_port = turn_ports["udp"][0]
        print(f"TURN UDP ポート: {udp_port}")

        # 制限前の WebRTC 統計情報を確認
        print("\n制限前の WebRTC 統計情報:")
        time.sleep(3)
        stats = sendonly.get_stats()
        show_webrtc_stats(stats)

        # 制限前の targetBitrate を確認 (video の全ての outbound-rtp を取得)
        simulcast_outbound_rtp_stats = [
            stat
            for stat in stats
            if stat.get("type") == "outbound-rtp" and stat.get("kind") == "video"
        ]
        assert len(simulcast_outbound_rtp_stats) > 0, "outbound-rtp (video) が取得できませんでした"

        # rid でソート (r0, r1, r2 の順)
        simulcast_outbound_rtp_stats.sort(key=lambda x: x.get("rid", ""))

        # simulcast が有効な場合は 3 つのストリーム (r0, r1, r2) が存在するはず
        assert len(simulcast_outbound_rtp_stats) == 3, (
            f"simulcast のストリーム数が不正: {len(simulcast_outbound_rtp_stats)} (期待値: 3)"
        )

        print("\n制限前の targetBitrate:")
        print(
            f"  rid={simulcast_outbound_rtp_stats[0].get('rid', 'none')}: {simulcast_outbound_rtp_stats[0]['targetBitrate']} bps ({simulcast_outbound_rtp_stats[0]['targetBitrate'] / 1000} kbps)"
        )
        print(
            f"  rid={simulcast_outbound_rtp_stats[1].get('rid', 'none')}: {simulcast_outbound_rtp_stats[1]['targetBitrate']} bps ({simulcast_outbound_rtp_stats[1]['targetBitrate'] / 1000} kbps)"
        )
        print(
            f"  rid={simulcast_outbound_rtp_stats[2].get('rid', 'none')}: {simulcast_outbound_rtp_stats[2]['targetBitrate']} bps ({simulcast_outbound_rtp_stats[2]['targetBitrate'] / 1000} kbps)"
        )

        # r2 (最高画質) のビットレートが MIN_BITRATE_BEFORE_LIMIT_KBPS 以上あることを確認
        r2_bitrate = simulcast_outbound_rtp_stats[2]["targetBitrate"]
        assert r2_bitrate >= MIN_BITRATE_BEFORE_LIMIT_KBPS * 1000, (
            f"制限前の r2 targetBitrate が想定より低い: {r2_bitrate} bps < {MIN_BITRATE_BEFORE_LIMIT_KBPS * 1000} bps"
        )

        # tc egress で帯域制限を設定
        with TCEgressManager(interface=interface) as tc:
            # 帯域制限を設定
            print(f"\nステップ 1: tc egress 帯域制限 {BANDWIDTH_LIMIT_KBPS}kbps を適用")
            tc.add_bandwidth_limit(rate_kbps=BANDWIDTH_LIMIT_KBPS)

            # tc の設定が存在することを確認
            print("\nステップ 2: tc 設定を確認")
            assert verify_tc_settings(interface), "tc の設定が確認できません"

            # tc の統計情報を表示 (適用直後)
            show_tc_stats(interface)

            # 接続を維持して帯域制限が有効な状態でテスト
            print("\nステップ 3: 帯域制限が有効な状態で接続を維持")
            time.sleep(10)

            # tc の統計情報を表示 (接続後)
            show_tc_stats(interface)

            # 統計情報を取得
            stats = tc.get_stats()
            print("\ntc 統計情報 (IPRoute):")
            for key, value in stats.items():
                print(f"  {key}: {value}")

            # WebRTC 統計情報を表示
            print("\nステップ 4: 制限後の WebRTC 統計情報を確認")
            stats = sendonly.get_stats()
            show_webrtc_stats(stats)

            # targetBitrate を確認 (video の全ての outbound-rtp を取得)
            simulcast_outbound_rtp_stats = [
                stat
                for stat in stats
                if stat.get("type") == "outbound-rtp" and stat.get("kind") == "video"
            ]
            assert len(simulcast_outbound_rtp_stats) > 0, (
                "outbound-rtp (video) が取得できませんでした"
            )

            # rid でソート (r0, r1, r2 の順)
            simulcast_outbound_rtp_stats.sort(key=lambda x: x.get("rid", ""))

            print("\n制限後の outbound-rtp 統計情報:")
            for stat in simulcast_outbound_rtp_stats:
                rid = stat.get("rid", "none")
                print(f"{rid} | outbound-rtp: {stats}")
                bitrate = stat.get("targetBitrate")
                if bitrate is not None:
                    print(f"  rid={rid}: targetBitrate={bitrate} bps ({bitrate / 1000} kbps)")
                else:
                    print(f"  rid={rid}: targetBitrate なし (停止中)")

            # 帯域制限により r1/r2 の targetBitrate 項目が存在しなくなる
            # r0 のみが targetBitrate を持つことを確認
            all_rids = [stat.get("rid") for stat in simulcast_outbound_rtp_stats]
            active_rids = [
                stat.get("rid") for stat in simulcast_outbound_rtp_stats if "targetBitrate" in stat
            ]
            print(f"\n確認: 存在する rid = {all_rids}")
            print(f"確認: targetBitrate を持つ rid = {active_rids}")
            print("期待値: targetBitrate を持つのは r0 のみ")

            # r0 のみが targetBitrate を持つことを確認
            assert active_rids == ["r0"], (
                f"帯域制限後は r0 のみが targetBitrate を持つはず: {active_rids}"
            )

            # r1 と r2 が存在する場合、targetBitrate が存在しないことを確認
            for stat in simulcast_outbound_rtp_stats:
                rid = stat.get("rid", "")
                if rid in ["r1", "r2"]:
                    assert "targetBitrate" not in stat, (
                        f"{rid} に targetBitrate が存在しています (停止しているはず)"
                    )
                    print(f"確認: {rid} は targetBitrate なし (停止中)")

            # r0 の targetBitrate が帯域制限以下であることを確認
            r0_stat = simulcast_outbound_rtp_stats[0]
            assert "targetBitrate" in r0_stat, "r0 に targetBitrate が存在しません"
            r0_bitrate = r0_stat["targetBitrate"]
            print(f"\n確認: r0 targetBitrate = {r0_bitrate} bps ({r0_bitrate / 1000} kbps)")
            print(f"期待値: {BANDWIDTH_LIMIT_KBPS} kbps 以下")

            # 多少のオーバーヘッドを考慮
            assert r0_bitrate <= BANDWIDTH_LIMIT_KBPS * 1000 * 1.2, (
                f"r0 targetBitrate が帯域制限を超えています: {r0_bitrate} bps > {BANDWIDTH_LIMIT_KBPS * 1000} bps"
            )

            print("\n帯域制限が有効な状態でテスト完了")

    # クリーンアップ確認
    print("\nクリーンアップ後の tc 設定:")
    show_tc_stats(interface)

    print("\n結果:")
    print("  ✓ テスト成功 (tc egress 帯域制限が適用された)")
    print("=" * 60 + "\n")
