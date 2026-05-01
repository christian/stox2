from datetime import datetime, timezone
from pathlib import Path
import os
import tempfile
import unittest

import polars as pl

from stox.storage import write_ticks


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


if __name__ == "__main__":
    unittest.main()
