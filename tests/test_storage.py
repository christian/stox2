from datetime import datetime, timezone
from pathlib import Path
import os
import tempfile
import unittest

import polars as pl

from stox.storage import write_bars, write_ticks


class WriteTicksTest(unittest.TestCase):
    def test_write_ticks_partitions_by_date_then_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_root = os.environ.get("STX_DATA_ROOT")
            os.environ["STX_DATA_ROOT"] = tmpdir
            try:
                df = pl.DataFrame(
                    {
                        "ts": [
                            datetime(2025, 2, 1, 14, 30, tzinfo=timezone.utc),
                            datetime(2025, 2, 2, 14, 30, tzinfo=timezone.utc),
                        ],
                        "last": [100.0, 101.0],
                        "size": [10, 20],
                    }
                )

                dataset_path = write_ticks(df, "AAPL")

                first_day = Path(dataset_path) / "date=2025-02-01" / "symbol=AAPL"
                second_day = Path(dataset_path) / "date=2025-02-02" / "symbol=AAPL"

                self.assertTrue(first_day.is_dir())
                self.assertTrue(second_day.is_dir())
                self.assertTrue(any(first_day.glob("*.parquet")))
                self.assertTrue(any(second_day.glob("*.parquet")))

                stored = pl.read_parquet(str(Path(dataset_path) / "**" / "*.parquet"))
                self.assertEqual(stored.columns, ["ts", "last", "size", "symbol", "date"])
            finally:
                if old_root is None:
                    os.environ.pop("STX_DATA_ROOT", None)
                else:
                    os.environ["STX_DATA_ROOT"] = old_root

    def test_write_bars_partitions_by_date_then_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_root = os.environ.get("STX_DATA_ROOT")
            os.environ["STX_DATA_ROOT"] = tmpdir
            try:
                df = pl.DataFrame(
                    {
                        "ts": [
                            datetime(2025, 2, 1, 14, 30, tzinfo=timezone.utc),
                            datetime(2025, 2, 2, 14, 30, tzinfo=timezone.utc),
                        ],
                        "open": [100.0, 101.0],
                        "high": [102.0, 103.0],
                        "low": [99.0, 100.0],
                        "close": [101.0, 102.0],
                        "volume": [1000, 2000],
                        "average": [100.5, 101.5],
                        "bar_count": [20, 30],
                    }
                )

                dataset_path = write_bars(df, "CRWV")

                first_day = Path(dataset_path) / "date=2025-02-01" / "symbol=CRWV"
                second_day = Path(dataset_path) / "date=2025-02-02" / "symbol=CRWV"

                self.assertTrue(first_day.is_dir())
                self.assertTrue(second_day.is_dir())
                self.assertTrue(any(first_day.glob("*.parquet")))
                self.assertTrue(any(second_day.glob("*.parquet")))

                stored = pl.read_parquet(str(Path(dataset_path) / "**" / "*.parquet"))
                self.assertEqual(
                    stored.columns,
                    [
                        "ts",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "average",
                        "bar_count",
                        "symbol",
                        "date",
                    ],
                )
            finally:
                if old_root is None:
                    os.environ.pop("STX_DATA_ROOT", None)
                else:
                    os.environ["STX_DATA_ROOT"] = old_root


if __name__ == "__main__":
    unittest.main()
