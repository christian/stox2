from datetime import datetime, timezone
import os
import math
import tempfile
import unittest

import polars as pl

from stox.explore import (
    describe_bars,
    load_bar_chart_series,
    load_bar_summary,
    load_bar_symbol_counts,
    load_intraday_indicator_series,
    load_intraday_research,
)
from stox.storage import write_bars


class ExploreTest(unittest.TestCase):
    def test_describe_and_summary_cover_written_bars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_root = os.environ.get("STX_DATA_ROOT")
            os.environ["STX_DATA_ROOT"] = tmpdir
            try:
                df = pl.DataFrame(
                    {
                        "ts": [
                            datetime(2025, 2, 1, 14, 30, tzinfo=timezone.utc),
                            datetime(2025, 2, 1, 14, 31, tzinfo=timezone.utc),
                            datetime(2025, 2, 1, 15, 0, tzinfo=timezone.utc),
                            datetime(2025, 2, 2, 14, 30, tzinfo=timezone.utc),
                            datetime(2025, 2, 2, 15, 0, tzinfo=timezone.utc),
                        ],
                        "open": [100.0, 101.0, 103.0, 102.0, 101.0],
                        "high": [101.0, 103.0, 104.0, 104.0, 102.0],
                        "low": [99.0, 100.0, 102.0, 101.0, 100.0],
                        "close": [101.0, 102.0, 103.5, 103.0, 100.5],
                        "volume": [10, 20, 30, 40, 50],
                    }
                )

                write_bars(df, "AAPL")
                benchmark_df = pl.DataFrame(
                    {
                        "ts": [
                            datetime(2025, 2, 1, 12, 0, tzinfo=timezone.utc),
                            datetime(2025, 2, 1, 13, 0, tzinfo=timezone.utc),
                            datetime(2025, 2, 2, 12, 0, tzinfo=timezone.utc),
                            datetime(2025, 2, 2, 13, 0, tzinfo=timezone.utc),
                        ],
                        "open": [500.0, 501.0, 510.0, 509.0],
                        "high": [502.0, 503.0, 511.0, 510.0],
                        "low": [499.0, 500.0, 507.0, 506.0],
                        "close": [501.0, 502.0, 509.0, 507.0],
                        "volume": [1000, 2000, 3000, 4000],
                    }
                )
                write_bars(benchmark_df, "QQQ")

                info = describe_bars()
                self.assertEqual(info.symbols, ["AAPL", "QQQ"])
                self.assertEqual(str(info.min_date), "2025-02-01")
                self.assertEqual(str(info.max_date), "2025-02-02")
                self.assertEqual(info.row_count, 9)
                self.assertGreater(info.disk_bytes, 0)

                summary = load_bar_summary(symbol="AAPL")
                self.assertEqual(summary["bars"].tolist(), [2, 3])
                self.assertEqual(summary["open_price"].tolist(), [102.0, 100.0])
                self.assertEqual(summary["high_price"].tolist(), [104.0, 104.0])
                self.assertEqual(summary["low_price"].tolist(), [100.0, 99.0])
                self.assertEqual(summary["close_price"].tolist(), [100.5, 103.5])
                self.assertAlmostEqual(summary["day_return_pct"].iloc[0], -1.4705882353)
                self.assertAlmostEqual(summary["prev_close_pct"].iloc[0], -2.8985507246)

                chart = load_bar_chart_series(symbol="AAPL", bucket="day")
                self.assertEqual(chart["open"].tolist(), [100.0, 102.0])
                self.assertEqual(chart["high"].tolist(), [104.0, 104.0])
                self.assertEqual(chart["low"].tolist(), [99.0, 100.0])
                self.assertEqual(chart["close"].tolist(), [103.5, 100.5])
                self.assertEqual(chart["volume"].tolist(), [60, 90])
                self.assertEqual(
                    chart["session_date"].astype(str).tolist(),
                    ["2025-02-01", "2025-02-02"],
                )

                symbol_counts = load_bar_symbol_counts()
                self.assertEqual(symbol_counts["symbol"].tolist(), ["AAPL", "QQQ"])
                self.assertEqual(symbol_counts["bars"].tolist(), [5, 4])

                research = load_intraday_research(symbol="AAPL", benchmark_symbol="QQQ")
                day_one = research[research["date"].astype(str) == "2025-02-01"].iloc[0]
                self.assertEqual(day_one["bars"], 3)
                self.assertEqual(day_one["open_price"], 100.0)
                self.assertEqual(day_one["high_price"], 104.0)
                self.assertEqual(day_one["low_price"], 99.0)
                self.assertEqual(day_one["close_price"], 103.5)
                self.assertEqual(day_one["volume"], 60)
                self.assertAlmostEqual(
                    day_one["vwap"],
                    (101.0 * 10 + 102.0 * 20 + 103.5 * 30) / 60,
                )
                self.assertEqual(day_one["benchmark_symbol"], "QQQ")
                self.assertAlmostEqual(day_one["benchmark_premarket_return_pct"], (502.0 / 500.0 - 1) * 100)
                self.assertAlmostEqual(day_one["benchmark_premarket_range_pct"], (503.0 - 499.0) / 500.0 * 100)
                self.assertAlmostEqual(day_one["benchmark_premarket_up_pct"], (503.0 / 500.0 - 1) * 100)
                self.assertAlmostEqual(day_one["benchmark_premarket_down_pct"], (499.0 / 500.0 - 1) * 100)
                self.assertEqual(day_one["benchmark_premarket_direction"], "UP")
                self.assertEqual(day_one["first_30m_price_direction"], "UP")
                self.assertTrue(day_one["benchmark_premarket_agrees_with_first_30m"])
                self.assertAlmostEqual(day_one["day_return_pct"], 3.5)
                ret_1m = (102.0 / 101.0 - 1) * 100
                ret_30m = (103.5 / 102.0 - 1) * 100
                self.assertAlmostEqual(
                    day_one["realized_vol_1m_pct"],
                    math.sqrt(ret_1m**2 + ret_30m**2),
                )
                self.assertAlmostEqual(day_one["realized_vol_30m_pct"], abs(ret_1m))
                self.assertAlmostEqual(day_one["rest_of_day_realized_vol_pct"], abs(ret_30m))
                self.assertAlmostEqual(day_one["first_30m_volume_pct"], 50.0)
                self.assertEqual(str(day_one["time_of_high"]), "2025-02-01 15:00:00")
                self.assertEqual(str(day_one["time_of_low"]), "2025-02-01 14:30:00")
                self.assertAlmostEqual(
                    day_one["max_intraday_drawdown_pct"],
                    (100.0 / 103.0 - 1) * 100,
                )
                self.assertAlmostEqual(day_one["first_5m_return_pct"], 2.0)
                self.assertAlmostEqual(day_one["first_15m_return_pct"], 2.0)
                self.assertAlmostEqual(day_one["first_30m_return_pct"], 2.0)
                self.assertAlmostEqual(day_one["opening_range_30m_pct"], 4.0)
                self.assertTrue(day_one["opening_range_broken_up"])
                self.assertFalse(day_one["opening_range_broken_down"])
                self.assertAlmostEqual(day_one["rest_of_day_return_pct"], (103.5 / 102.0 - 1) * 100)
                self.assertAlmostEqual(
                    day_one["close_vs_vwap_pct"],
                    (103.5 / ((101.0 * 10 + 102.0 * 20 + 103.5 * 30) / 60) - 1) * 100,
                )
                self.assertAlmostEqual(day_one["max_favorable_from_open_pct"], 4.0)
                self.assertAlmostEqual(day_one["max_adverse_from_open_pct"], -1.0)
                self.assertAlmostEqual(day_one["biggest_1m_up_pct"], (103.5 / 102.0 - 1) * 100)

                indicator_series = load_intraday_indicator_series(
                    symbol="AAPL",
                    session_date=datetime(2025, 2, 1).date(),
                )
                self.assertEqual(indicator_series["close"].tolist(), [101.0, 102.0, 103.5])
                self.assertEqual(indicator_series["session_open"].tolist(), [100.0, 100.0, 100.0])
                self.assertEqual(
                    indicator_series["opening_range_high_30m"].tolist(),
                    [103.0, 103.0, 103.0],
                )
                self.assertEqual(
                    indicator_series["opening_range_low_30m"].tolist(),
                    [99.0, 99.0, 99.0],
                )
                self.assertAlmostEqual(indicator_series["vwap"].iloc[0], 101.0)
                self.assertAlmostEqual(
                    indicator_series["vwap"].iloc[1],
                    (101.0 * 10 + 102.0 * 20) / 30,
                )
                self.assertAlmostEqual(
                    indicator_series["vwap"].iloc[2],
                    (101.0 * 10 + 102.0 * 20 + 103.5 * 30) / 60,
                )
            finally:
                if old_root is None:
                    os.environ.pop("STX_DATA_ROOT", None)
                else:
                    os.environ["STX_DATA_ROOT"] = old_root


if __name__ == "__main__":
    unittest.main()
