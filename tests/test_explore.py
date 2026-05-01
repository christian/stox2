from datetime import datetime, timezone
import os
import tempfile
import unittest

import polars as pl

from stox.explore import describe_ticks, load_chart_series, load_tick_summary
from stox.storage import write_ticks


class ExploreTest(unittest.TestCase):
    def test_describe_and_summary_cover_written_ticks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_root = os.environ.get("STX_DATA_ROOT")
            os.environ["STX_DATA_ROOT"] = tmpdir
            try:
                df = pl.DataFrame(
                    {
                        "ts": [
                            datetime(2025, 2, 1, 14, 30, tzinfo=timezone.utc),
                            datetime(2025, 2, 1, 14, 31, tzinfo=timezone.utc),
                            datetime(2025, 2, 2, 14, 30, tzinfo=timezone.utc),
                        ],
                        "last": [100.0, 101.0, 102.0],
                        "size": [10, 20, 30],
                    }
                )

                write_ticks(df, "AAPL")

                info = describe_ticks()
                self.assertEqual(info.symbols, ["AAPL"])
                self.assertEqual(str(info.min_date), "2025-02-01")
                self.assertEqual(str(info.max_date), "2025-02-02")
                self.assertEqual(info.row_count, 3)
                self.assertGreater(info.disk_bytes, 0)

                summary = load_tick_summary(symbol="AAPL")
                self.assertEqual(summary["rows"].tolist(), [1, 2])
                self.assertEqual(summary["close_price"].tolist(), [102.0, 101.0])
                self.assertAlmostEqual(summary["prev_close_pct"].iloc[0], 0.9900990099)

                chart = load_chart_series(symbol="AAPL", bucket="day")
                self.assertEqual(chart["close_price"].tolist(), [101.0, 102.0])
                self.assertEqual(chart["session_date"].astype(str).tolist(), ["2025-02-01", "2025-02-02"])
            finally:
                if old_root is None:
                    os.environ.pop("STX_DATA_ROOT", None)
                else:
                    os.environ["STX_DATA_ROOT"] = old_root


if __name__ == "__main__":
    unittest.main()
