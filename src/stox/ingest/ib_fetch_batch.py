from __future__ import annotations

import argparse
import time
from dataclasses import replace
from pathlib import Path
from typing import Iterable, List

from .ib_fetch import FetchConfig, _parse_dt, fetch_ticks
from ..storage import write_ticks


def _parse_symbols(value: str | None) -> List[str]:
    if not value:
        return []
    return [s.strip().upper() for s in value.split(",") if s.strip()]


def _read_symbols_file(path: Path) -> List[str]:
    raw = path.read_text().splitlines()
    return [line.strip().upper() for line in raw if line.strip() and not line.startswith("#")]


def _iter_symbols(symbols: List[str], file_path: Path | None) -> Iterable[str]:
    seen = set()
    for sym in symbols:
        if sym not in seen:
            seen.add(sym)
            yield sym
    if file_path:
        for sym in _read_symbols_file(file_path):
            if sym not in seen:
                seen.add(sym)
                yield sym


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch IB historical ticks for many symbols and store as Parquet"
    )
    parser.add_argument("--symbols", help="Comma-separated list, e.g. AAPL,MSFT")
    parser.add_argument("--symbols-file", help="Path to newline-delimited symbols file")
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
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds to wait between symbols")

    args = parser.parse_args()

    symbols = _parse_symbols(args.symbols)
    symbols_file = Path(args.symbols_file).expanduser() if args.symbols_file else None
    symbols_iter = list(_iter_symbols(symbols, symbols_file))

    if not symbols_iter:
        raise SystemExit("No symbols provided. Use --symbols or --symbols-file.")

    base = FetchConfig(
        symbol="",
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

    for idx, symbol in enumerate(symbols_iter, start=1):
        cfg = replace(base, symbol=symbol)
        try:
            df = fetch_ticks(cfg)
            if df.is_empty():
                print(f"[{idx}/{len(symbols_iter)}] {symbol}: no ticks returned")
            else:
                path = write_ticks(df, cfg.symbol)
                print(f"[{idx}/{len(symbols_iter)}] {symbol}: wrote {df.height} ticks to {path}")
        except Exception as exc:
            print(f"[{idx}/{len(symbols_iter)}] {symbol}: ERROR {exc}")

        if idx < len(symbols_iter):
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()
