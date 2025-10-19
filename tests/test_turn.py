import time

from client import SoraClient, SoraRole


def test_turn_ports(settings):
    """TURN ポートが正しく取得できることを確認する"""
    with SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=True,
        video=False,
    ) as sendonly:
        time.sleep(3)

        # offer_message が受信されていることを確認
        assert sendonly.offer_message is not None

        # turn_ports プロパティから TURN ポートを取得
        turn_ports = sendonly.turn_ports

        # turn_ports が辞書であることを確認
        assert isinstance(turn_ports, dict)

        # 必須キーが存在することを確認
        assert "udp" in turn_ports
        assert "tcp" in turn_ports
        assert "tls" in turn_ports

        # 各値がリストであることを確認
        assert isinstance(turn_ports["udp"], list)
        assert isinstance(turn_ports["tcp"], list)
        assert isinstance(turn_ports["tls"], list)

        # UDP ポートは必ず1つ以上存在する
        assert len(turn_ports["udp"]) > 0, "UDP ポートが取得できていません"

        # UDP ポートがエフェメラルポート範囲内であることを確認
        for port in turn_ports["udp"]:
            assert 49152 <= port <= 65535, f"UDP ポートがエフェメラルポート範囲外: {port}"

        # デバッグ用にポート情報を出力
        print(f"TURN ports (UDP): {turn_ports['udp']}")
        print(f"TURN ports (TCP): {turn_ports['tcp']}")
        print(f"TURN ports (TLS): {turn_ports['tls']}")

        # offer_message の config.iceServers を確認
        if "config" in sendonly.offer_message:
            config = sendonly.offer_message["config"]
            if "iceServers" in config:
                print(f"ICE Servers: {config['iceServers']}")

        sendonly.disconnect()
