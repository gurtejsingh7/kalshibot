import argparse
import json
import time
import datetime as dt
from typing import Dict, Any, List, Tuple, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

import config
from kalshi_client import KalshiClient

console = Console()

# ---------- formatting ----------
def cents_to_dollars(cents: int) -> str:
    return f"${(cents or 0) / 100:,.2f}"

def ts_to_iso(ts_seconds: int) -> str:
    return dt.datetime.fromtimestamp(ts_seconds or 0).strftime("%Y-%m-%d %H:%M:%S UTC")

# ---------- classification & styling ----------
SPORT_KEYS = ("NBA","NFL","MLB","NHL","EPL","NCAAMB","NCAAF","ATP","WTA","NCAAMBGAME","GAME","MATCH")
POLICY_KEYS = ("TRUMP","BIDEN","ELECTION","SENATE","HOUSE","FED","INFLATION","CPI","RATE")

def classify_market(m: Dict[str, Any]) -> str:
    t = (m.get("ticker") or "").upper()
    title = (m.get("title") or "").upper()
    if any(k in t or k in title for k in SPORT_KEYS): return "sports"
    if any(k in t or k in title for k in POLICY_KEYS): return "politics"
    return "other"

ROW_STYLE = {"sports": "bright_cyan", "politics": "magenta", "other": "white"}

# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="Kalshi Demo Client")
    p.add_argument("--status", default="open", help="Market status filter (default: open)")
    p.add_argument("--limit", type=int, default=15, help="Number of markets to list (single page)")
    p.add_argument("--all", action="store_true", help="Fetch all pages with cursor pagination")
    p.add_argument("--page-limit", type=int, default=100, help="Items per page when paginating (1-1000)")
    p.add_argument("--search", default="", help="Substring filter over title/ticker")
    p.add_argument("--sort", choices=["title","ticker","yes_price","no_price"], default="title",
                   help="Sort key for markets (metadata fields)")
    p.add_argument("--json", action="store_true", help="Print raw JSON instead of tables")
    p.add_argument("--save", default="", help="Write markets JSON to this path")
    p.add_argument("--refresh", type=int, default=0, help="Seconds between refresh; 0 = single run")
    p.add_argument("--iterations", type=int, default=1, help="Refresh iterations when --refresh > 0")
    p.add_argument("--debug-path", default="", help="GET arbitrary API path and dump JSON, e.g. /markets/XYZ/orderbook")
    p.add_argument("--debug-ticker", default="", help="Dump raw orderbook JSON for a ticker and exit")
    return p.parse_args()

# ---------- orderbook helpers per docs ----------
def fetch_orderbook(client: KalshiClient, ticker: str) -> Optional[Dict[str, Any]]:
    ob = client.request("GET", f"/markets/{ticker}/orderbook")
    if ob and isinstance(ob, dict) and ("orderbook" in ob or "yes" in ob or "no" in ob):
        return ob
    return None

def parse_best_prices(ob: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """
    Docs: {"orderbook":{"yes":[[price,qty],...],"no":[[price,qty],...]}} (ascending by price)
    Best bids are the last elements.
    Implied asks:
      YES_ASK = 100 - NO_BID
      NO_ASK  = 100 - YES_BID
    Returns strings (cents) for display.
    """
    # normalize
    if "orderbook" in ob and isinstance(ob["orderbook"], dict):
        yes = ob["orderbook"].get("yes") or []
        no  = ob["orderbook"].get("no") or []
    else:
        yes = ob.get("yes") or []
        no  = ob.get("no") or []

    def last_price(arr):
        if arr and isinstance(arr[-1], (list, tuple)) and len(arr[-1]) >= 1:
            return arr[-1][0]
        return None

    yb = last_price(yes)
    nb = last_price(no)
    ya = (100 - nb) if nb is not None else None
    na = (100 - yb) if yb is not None else None

    to_s = lambda v: "" if v is None else str(v)
    return to_s(yb), to_s(ya), to_s(nb), to_s(na)

def cents_as_dollars_str(x: str) -> str:
    if not x: return ""
    try:
        return f"${int(x)/100:,.2f}"
    except ValueError:
        return x

# ---------- rendering ----------
def render_balance(bal: Dict[str, Any]):
    panel = Panel.fit(
        f"[bold]Cash:[/bold] {cents_to_dollars(bal.get('balance', 0))}  "
        f"[bold]Portfolio:[/bold] {cents_to_dollars(bal.get('portfolio_value', 0))}  "
        f"[bold]Updated:[/bold] {ts_to_iso(bal.get('updated_ts', 0))}",
        title="Account Balance",
        border_style="green",
    )
    console.print(panel)

def render_markets_with_prices(client: KalshiClient, markets: List[Dict[str, Any]], status: str,
                               limit: int, subtitle_extra: str = ""):
    table = Table(title=f"Markets (status={status}, limit={limit}) {subtitle_extra}".strip(),
                  box=box.SIMPLE_HEAVY)
    table.add_column("Ticker", style="cyan", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("YES Bid", justify="right", style="green")
    table.add_column("YES Ask", justify="right", style="green")
    table.add_column("NO Bid", justify="right", style="red")
    table.add_column("NO Ask", justify="right", style="red")

    for m in markets:
        ticker = m.get("ticker","")
        title  = m.get("title","")
        ob = fetch_orderbook(client, ticker)
        yb, ya, nb, na = ("","","","")
        if ob:
            yb, ya, nb, na = parse_best_prices(ob)
        rstyle = ROW_STYLE[classify_market(m)]
        table.add_row(ticker, title, cents_as_dollars_str(yb), cents_as_dollars_str(ya),
                      cents_as_dollars_str(nb), cents_as_dollars_str(na), style=rstyle)

    console.print(table)

# ---------- pipeline ----------
def main():
    args = parse_args()
    client = KalshiClient(config.API_KEY_ID, config.PRIVATE_KEY_PATH, config.BASE_URL)

    # Debug paths early-exit
    if args.debug_path:
        data = client.request("GET", args.debug_path)
        console.print(f"[dim]GET {args.debug_path}[/dim]")
        console.print_json(data=data if data else {})
        return
    if args.debug_ticker:
        path = f"/markets/{args.debug_ticker}/orderbook"
        data = client.request("GET", path)
        console.print(f"[dim]GET {path}[/dim]")
        console.print_json(data=data if data else {})
        return

    cycles = args.iterations if args.refresh > 0 else 1
    for i in range(cycles):
        console.rule("[bold green]Kalshi Bot[/bold green]")

        # Balance
        bal = client.get_balance()
        if not bal:
            console.print("[red]Failed to fetch balance.[/red]")
            return
        if args.json:
            console.print_json(data=bal)
        else:
            render_balance(bal)

        # Markets (single page or paginated)
        if args.all:
            items = list(client.paginate("/markets", limit=args.page_limit, params={"status": args.status}, key="markets"))
            mkts = items
        else:
            raw = client.list_markets(status=args.status, limit=args.limit)
            mkts = raw.get("markets", []) if raw else []

        # Filter
        q = args.search.strip().lower()
        if q:
            mkts = [m for m in mkts if q in (m.get("title","").lower()) or q in (m.get("ticker","").lower())]

        # Sort by metadata field (if present)
        key = args.sort
        def keyfn(m):
            if key == "title": return m.get("title","")
            if key == "ticker": return m.get("ticker","")
            if key == "yes_price": return m.get("yes_price") if m.get("yes_price") is not None else -1
            if key == "no_price":  return m.get("no_price")  if m.get("no_price")  is not None else -1
            return m.get("title","")
        mkts = sorted(mkts, key=keyfn)

        if args.save:
            snap = {
                "fetched_at": ts_to_iso(int(time.time())),
                "status": args.status,
                "limit": args.limit,
                "all": args.all,
                "page_limit": args.page_limit,
                "search": args.search,
                "sort": args.sort,
                "markets": mkts,
            }
            with open(args.save, "w", encoding="utf-8") as f:
                json.dump(snap, f, indent=2)
            console.print(f"[dim]Saved snapshot to {args.save}[/dim]")

        if args.json:
            console.print_json(data={"markets": mkts})
        else:
            subtitle = f"(search='{args.search}', sort={args.sort})" if args.search or args.sort else ""
            render_markets_with_prices(client, mkts, args.status, args.limit if not args.all else len(mkts), subtitle_extra=subtitle)

        if args.refresh > 0 and i < cycles - 1:
            time.sleep(args.refresh)

if __name__ == "__main__":
    main()
