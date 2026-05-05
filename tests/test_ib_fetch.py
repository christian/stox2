from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from stox.ingest.ib_fetch import FetchConfig, fetch_ticks


class FakeIB:
    def __init__(self) -> None:
        self.connected = False
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.qualify_calls = 0
        self.req_calls = 0

    def connect(self, host: str, port: int, clientId: int) -> None:
        self.connected = True
        self.connect_calls += 1

    def qualifyContracts(self, contract) -> None:
        self.qualify_calls += 1

    def reqHistoricalTicks(self, contract, **kwargs):
        self.req_calls += 1
        if self.req_calls == 1:
            self.connected = False
            raise ConnectionError("socket disconnected")

        return [
            SimpleNamespace(
                time=datetime(2025, 2, 1, 14, 30, tzinfo=timezone.utc),
                price=100.0,
                size=10,
                exchange="TEST",
                specialConditions="",
            ),
            SimpleNamespace(
                time=datetime(2025, 2, 1, 14, 31, 59, tzinfo=timezone.utc),
                price=101.0,
                size=20,
                exchange="TEST",
                specialConditions="",
            ),
        ]

    def isConnected(self) -> bool:
        return self.connected

    def disconnect(self) -> None:
        self.connected = False
        self.disconnect_calls += 1


class FetchTicksReconnectTest(unittest.TestCase):
    @patch("stox.ingest.ib_fetch.time.sleep", return_value=None)
    def test_fetch_ticks_reconnects_and_resumes(self, sleep_mock) -> None:
        cfg = FetchConfig(
            symbol="AAPL",
            exchange="SMART",
            currency="USD",
            start=datetime(2025, 2, 1, 14, 30, tzinfo=timezone.utc),
            end=datetime(2025, 2, 1, 14, 32, tzinfo=timezone.utc),
            what="TRADES",
            max_ticks=10,
            use_rth=False,
            host="127.0.0.1",
            port=4001,
            client_id=7,
            reconnect_retries=2,
            retry_delay_seconds=0.1,
        )

        ib = FakeIB()
        with patch("stox.ingest.ib_fetch.IB", return_value=ib), patch(
            "stox.ingest.ib_fetch.Stock",
            new=lambda symbol, exchange, currency: (symbol, exchange, currency),
        ):
            df = fetch_ticks(cfg)

        self.assertEqual(df["last"].to_list(), [100.0, 101.0])
        self.assertEqual(df["size"].to_list(), [10, 20])
        self.assertEqual(ib.connect_calls, 2)
        self.assertEqual(ib.qualify_calls, 2)
        self.assertEqual(ib.req_calls, 2)
        sleep_mock.assert_called_once_with(0.1)


if __name__ == "__main__":
    unittest.main()
