from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List

import polars as pl
from ib_insync import IB, Stock

from ..storage import write_ticks


@dataclass(frozen=True)
class FetchConfig:
    symbol: str
    exchange: str
    currency: str
    start: datetime
    end: datetime
    what: str
    max_ticks: int
    use_rth: bool
    host: str
    port: int
    client_id: int


def _parse_dt(value: str) -> datetime:
    # Accept ISO-8601 with timezone. If no timezone, assume UTC.
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ticks_to_frame(what: str, ticks: Iterable) -> pl.DataFrame:
    rows: List[dict] = []
    if what == "TRADES":
        for t in ticks:
            rows.append(
                {
                    "ts": t.time,
                    "last": t.price,
                    "size": t.size,
                    "exchange": t.exchange,
                    "conditions": t.specialConditions,
                }
            )
    elif what == "BID_ASK":
        for t in ticks:
            rows.append(
                {
                    "ts": t.time,
                    "bid": t.bidPrice,
                    "ask": t.askPrice,
                    "bid_size": t.bidSize,
                    "ask_size": t.askSize,
                }
            )
    else:
        raise ValueError(f"unsupported what={what}")

    if not rows:
        return pl.DataFrame(schema=[("ts", pl.Datetime)])

    return pl.DataFrame(rows)


def fetch_ticks(cfg: FetchConfig) -> pl.DataFrame:
    ib = IB()
    try:
        ib.connect(cfg.host, cfg.port, clientId=cfg.client_id)

        contract = Stock(cfg.symbol, cfg.exchange, cfg.currency)
        ib.qualifyContracts(contract)

        all_ticks: List = []
        cursor = cfg.start

        # IB typically limits historical tick responses (~1000 ticks per call).
        while cursor < cfg.end and len(all_ticks) < cfg.max_ticks:
            remaining = cfg.max_ticks - len(all_ticks)
            batch = ib.reqHistoricalTicks(
                contract,
                startDateTime=cursor,
                endDateTime=cfg.end,
                numberOfTicks=min(1000, remaining),
                whatToShow=cfg.what,
                useRth=cfg.use_rth,
                ignoreSize=False,
            )
            if not batch:
                break

            all_ticks.extend(batch)
            last_ts = batch[-1].time
            cursor = last_ts + timedelta(seconds=1)

        return _ticks_to_frame(cfg.what, all_ticks)
    finally:
        if ib.isConnected():
            ib.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch IB historical ticks and store as Parquet")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--exchange", default="SMART")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--what", choices=["TRADES", "BID_ASK"], default="TRADES")
    parser.add_argument("--max", dest="max_ticks", type=int, default=5000)
    parser.add_argument("--use-rth", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7497)
    parser.add_argument("--client-id", type=int, default=7)

    args = parser.parse_args()

    cfg = FetchConfig(
        symbol=args.symbol,
        exchange=args.exchange,
        currency=args.currency,
        start=_parse_dt(args.start),
        end=_parse_dt(args.end),
        what=args.what,
        max_ticks=args.max_ticks,
        use_rth=args.use_rth,
        host=args.host,
        port=args.port,
        client_id=args.client_id,
    )

    df = fetch_ticks(cfg)
    if df.is_empty():
        print("No ticks returned.")
        return

    path = write_ticks(df, cfg.symbol)
    print(f"Wrote {df.height} ticks to {path}")


if __name__ == "__main__":
    main()
