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
BANDWIDTH_OVERHEAD_FACTOR = 1.2  # 帯域制限の許容オーバーヘッド (20%)


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

        # tc qdisc の情報を取得する (tbf または netem qdisc のみ)
        for qdisc in self.ipr.get_qdiscs(idx):
            kind = qdisc.get_attr("TCA_KIND")
            if kind not in ("tbf", "netem"):
                continue

            # TCA_STATS2 属性から統計情報を取得
            stats2 = qdisc.get_attr("TCA_STATS2")
            if not stats2:
                continue

            # TCA_STATS_BASIC から bytes と packets を取得
            stats_basic = stats2.get_attr("TCA_STATS_BASIC")
            sent_bytes = stats_basic.get("bytes", 0) if stats_basic else 0
            sent_packets = stats_basic.get("packets", 0) if stats_basic else 0

            # TCA_STATS_QUEUE から drops, overlimits, requeues を取得
            stats_queue = stats2.get_attr("TCA_STATS_QUEUE")
            if stats_queue:
                drops = stats_queue.get("drops", 0)
                overlimits = stats_queue.get("overlimits", 0)
                requeues = stats_queue.get("requeues", 0)
            else:
                drops = 0
                overlimits = 0
                requeues = 0

            return {
                "sent_bytes": sent_bytes,
                "sent_packets": sent_packets,
                "drops": drops,
                "overlimits": overlimits,
                "requeues": requeues,
            }

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

            # qdisc の情報を取得して表示 (tbf/netem のみ)
            print(f"\ntc 統計情報 ({interface}):")
            found = False
            for qdisc in ipr.get_qdiscs(idx):
                kind = qdisc.get_attr("TCA_KIND")
                # tbf または netem qdisc のみを表示
                if kind not in ("tbf", "netem"):
                    continue

                found = True
                handle = qdisc.get("handle", 0)
                parent = qdisc.get("parent", 0)

                # TCA_STATS2 属性から統計情報を取得
                stats2 = qdisc.get_attr("TCA_STATS2")
                if not stats2:
                    continue

                # TCA_STATS_BASIC から bytes と packets を取得
                stats_basic = stats2.get_attr("TCA_STATS_BASIC")
                if stats_basic:
                    sent_bytes = stats_basic.get("bytes", 0)
                    sent_packets = stats_basic.get("packets", 0)
                else:
                    sent_bytes = 0
                    sent_packets = 0

                # TCA_STATS_QUEUE から drops と overlimits を取得
                stats_queue = stats2.get_attr("TCA_STATS_QUEUE")
                if stats_queue:
                    drops = stats_queue.get("drops", 0)
                    overlimits = stats_queue.get("overlimits", 0)
                else:
                    drops = 0
                    overlimits = 0

                print(f"  qdisc {kind} handle {handle:#x} parent {parent:#x}")
                print(f"    Sent {sent_bytes} bytes {sent_packets} packets")
                print(f"    drops {drops}, overlimits {overlimits}")

            if not found:
                print("  (tc 設定なし)")
    except Exception as e:
        print(f"tc 統計情報の取得に失敗: {e}")


def get_simulcast_outbound_rtp_stats(webrtc_stats: list) -> list:
    """simulcast の outbound-rtp 統計情報を取得してソートする。

    Args:
        webrtc_stats: get_stats() で取得した統計情報のリスト

    Returns:
        rid でソートされた outbound-rtp 統計情報のリスト
    """
    simulcast_stats = [
        stat
        for stat in webrtc_stats
        if stat.get("type") == "outbound-rtp" and stat.get("kind") == "video"
    ]
    simulcast_stats.sort(key=lambda x: x.get("rid", ""))
    return simulcast_stats


def show_webrtc_stats(webrtc_stats: list) -> None:
    """WebRTC の統計情報を表示する。

    Args:
        webrtc_stats: get_stats() で取得した統計情報のリスト
    """
    try:
        print("\nWebRTC 統計情報:")
        for stat in webrtc_stats:
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
        webrtc_stats = sendonly.get_stats()
        show_webrtc_stats(webrtc_stats)

        # 制限前の targetBitrate を確認 (video の全ての outbound-rtp を取得)
        simulcast_outbound_rtp_stats = get_simulcast_outbound_rtp_stats(webrtc_stats)

        # simulcast では r0/r1/r2 の 3 つのストリームが必ず存在する
        assert len(simulcast_outbound_rtp_stats) == 3

        # r0 の確認
        outbound_rtp_r0 = simulcast_outbound_rtp_stats[0]
        assert "rid" in outbound_rtp_r0
        assert outbound_rtp_r0["rid"] == "r0"
        assert "targetBitrate" in outbound_rtp_r0

        # r1 の確認
        outbound_rtp_r1 = simulcast_outbound_rtp_stats[1]
        assert "rid" in outbound_rtp_r1
        assert outbound_rtp_r1["rid"] == "r1"
        assert "targetBitrate" in outbound_rtp_r1

        # r2 の確認
        outbound_rtp_r2 = simulcast_outbound_rtp_stats[2]
        assert "rid" in outbound_rtp_r2
        assert outbound_rtp_r2["rid"] == "r2"
        assert "targetBitrate" in outbound_rtp_r2

        print("\nBefore bandwidth limit - targetBitrate:")
        print(
            f"  rid={outbound_rtp_r0['rid']}: {outbound_rtp_r0['targetBitrate']} bps "
            f"({outbound_rtp_r0['targetBitrate'] / 1000} kbps)"
        )
        print(
            f"  rid={outbound_rtp_r1['rid']}: {outbound_rtp_r1['targetBitrate']} bps "
            f"({outbound_rtp_r1['targetBitrate'] / 1000} kbps)"
        )
        print(
            f"  rid={outbound_rtp_r2['rid']}: {outbound_rtp_r2['targetBitrate']} bps "
            f"({outbound_rtp_r2['targetBitrate'] / 1000} kbps)"
        )

        # r2 (最高画質) のビットレートが MIN_BITRATE_BEFORE_LIMIT_KBPS 以上あることを確認
        assert outbound_rtp_r2["targetBitrate"] >= MIN_BITRATE_BEFORE_LIMIT_KBPS * 1000

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
            tc_stats = tc.get_stats()
            print("\ntc 統計情報 (IPRoute):")
            for key, value in tc_stats.items():
                print(f"  {key}: {value}")

            # WebRTC 統計情報を表示
            print("\nステップ 4: 制限後の WebRTC 統計情報を確認")
            webrtc_stats_after = sendonly.get_stats()
            show_webrtc_stats(webrtc_stats_after)

            # targetBitrate を確認 (video の全ての outbound-rtp を取得)
            simulcast_outbound_rtp_stats = get_simulcast_outbound_rtp_stats(webrtc_stats_after)

            # simulcast では r0/r1/r2 の 3 つのストリームが必ず存在する
            assert len(simulcast_outbound_rtp_stats) == 3

            # r0/r1/r2 の確認
            outbound_rtp_r0 = simulcast_outbound_rtp_stats[0]
            assert "rid" in outbound_rtp_r0
            assert outbound_rtp_r0["rid"] == "r0"

            outbound_rtp_r1 = simulcast_outbound_rtp_stats[1]
            assert "rid" in outbound_rtp_r1
            assert outbound_rtp_r1["rid"] == "r1"

            outbound_rtp_r2 = simulcast_outbound_rtp_stats[2]
            assert "rid" in outbound_rtp_r2
            assert outbound_rtp_r2["rid"] == "r2"

            print("\nAfter bandwidth limit - outbound-rtp stats:")
            for stat in simulcast_outbound_rtp_stats:
                rid = stat.get("rid", "none")
                bitrate = stat.get("targetBitrate")
                quality_limitation = stat.get("qualityLimitationReason", "none")
                if bitrate is not None:
                    print(
                        f"  rid={rid}: targetBitrate={bitrate} bps ({bitrate / 1000} kbps), "
                        f"qualityLimitationReason={quality_limitation}"
                    )
                else:
                    print(
                        f"  rid={rid}: targetBitrate=none (paused), "
                        f"qualityLimitationReason={quality_limitation}"
                    )

            # r0 の確認: targetBitrate が存在し、帯域制限以下であること
            assert "targetBitrate" in outbound_rtp_r0
            r0_bitrate = outbound_rtp_r0["targetBitrate"]
            assert r0_bitrate <= BANDWIDTH_LIMIT_KBPS * 1000 * BANDWIDTH_OVERHEAD_FACTOR
            assert "qualityLimitationReason" in outbound_rtp_r0
            assert outbound_rtp_r0["qualityLimitationReason"] == "bandwidth"
            print(
                f"\nVerify r0: targetBitrate={r0_bitrate} bps ({r0_bitrate / 1000} kbps), "
                f"qualityLimitationReason={outbound_rtp_r0['qualityLimitationReason']}"
            )

            # r1 の確認: targetBitrate が存在せず、qualityLimitationReason が bandwidth であること
            assert "targetBitrate" not in outbound_rtp_r1
            assert "qualityLimitationReason" in outbound_rtp_r1
            assert outbound_rtp_r1["qualityLimitationReason"] == "bandwidth"
            print(
                f"Verify r1: targetBitrate=none (paused), qualityLimitationReason={outbound_rtp_r1['qualityLimitationReason']}"
            )

            # r2 の確認: targetBitrate が存在せず、qualityLimitationReason が bandwidth であること
            assert "targetBitrate" not in outbound_rtp_r2
            assert "qualityLimitationReason" in outbound_rtp_r2
            assert outbound_rtp_r2["qualityLimitationReason"] == "bandwidth"
            print(
                f"Verify r2: targetBitrate=none (paused), qualityLimitationReason={outbound_rtp_r2['qualityLimitationReason']}"
            )

            print("\nTest completed with bandwidth limit applied")

    # クリーンアップ確認
    print("\nAfter cleanup - tc settings:")
    show_tc_stats(interface)

    print("\nResult:")
    print("  ✓ Test passed: tc egress bandwidth limit applied successfully")
    print("=" * 60 + "\n")
