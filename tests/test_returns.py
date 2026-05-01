from datetime import datetime, timezone
import unittest

import polars as pl

from stox.features.returns import forward_returns


class ForwardReturnsTest(unittest.TestCase):
    def test_forward_returns_use_first_tick_at_or_after_horizon(self) -> None:
        df = pl.DataFrame(
            {
                "ts": [
                    datetime(2025, 2, 1, 14, 30, tzinfo=timezone.utc),
                    datetime(2025, 2, 1, 14, 31, tzinfo=timezone.utc),
                    datetime(2025, 2, 1, 15, 35, tzinfo=timezone.utc),
                ],
                "last": [100.0, 110.0, 121.0],
            }
        )

        out = forward_returns(df, horizon_minutes=60)

        self.assertAlmostEqual(out["ret_1tick"][0], 0.10)
        self.assertAlmostEqual(out["ret_1tick"][1], 0.10)
        self.assertIsNone(out["ret_1tick"][2])

        self.assertAlmostEqual(out["ret_fwd"][0], 0.21)
        self.assertAlmostEqual(out["ret_fwd"][1], 0.10)
        self.assertIsNone(out["ret_fwd"][2])


if __name__ == "__main__":
    unittest.main()
