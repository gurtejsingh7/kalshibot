import argparse
import json
import time
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

import config
from kalshi_client import KalshiClient

console = Console()

# ---------- formatting helpers ----------


def cents_to_dollars(cents: int) -> str:
    return f"${(cents or 0) / 100:,.2f}"


def ts_to_iso(ts_seconds: int) -> str:
    return dt.datetime.fromtimestamp(ts_seconds or 0).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def parse_iso8601(ts: Optional[str]) -> str:
    if not ts:
        return ""
    # API typically returns ISO8601 like "2023-11-07T05:31:56Z"
    return ts.replace("T", " ").replace("Z", " UTC")


# ---------- classification for row colours ----------

SPORT_KEYS = (
    "NBA",
    "NFL",
    "MLB",
    "NHL",
    "EPL",
    "NCAAMB",
    "NCAAF",
    "ATP",
    "WTA",
    "NCAAMBGAME",
    "GAME",
    "MATCH",
)
POLICY_KEYS = (
    "TRUMP",
    "BIDEN",
    "ELECTION",
    "SENATE",
    "HOUSE",
    "FED",
    "INFLATION",
    "CPI",
    "RATE",
)

ROW_STYLE = {"sports": "bright_cyan", "politics": "magenta", "other": "white"}


def classify_market(m: Dict[str, Any]) -> str:
    t = (m.get("ticker") or "").upper()
    title = (m.get("title") or "").upper()
    if any(k in t or k in title for k in SPORT_KEYS):
        return "sports"
    if any(k in t or k in title for k in POLICY_KEYS):
        return "politics"
    return "other"


# ---------- orderbook helpers ----------


def fetch_orderbook(client: KalshiClient, ticker: str) -> Optional[Dict[str, Any]]:
    """GET /markets/{ticker}/orderbook and return JSON (or None on failure)."""
    ob = client.request("GET", f"/markets/{ticker}/orderbook")
    if ob and isinstance(ob, dict):
        return ob
    return None


def parse_best_prices(
    ob: Dict[str, Any],
) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """
    Parse best YES and NO bids (and implied asks) from an orderbook.

    Expected shape (per Kalshi docs):
      {
        "orderbook": {
          "yes": [[price, qty], ...],  # ascending by price
          "no":  [[price, qty], ...]
        }
      }

    Returns (yes_bid, yes_ask, no_bid, no_ask) in cents, or None where missing.
    """
    if "orderbook" in ob and isinstance(ob["orderbook"], dict):
        yes = ob["orderbook"].get("yes") or []
        no = ob["orderbook"].get("no") or []
    else:
        yes = ob.get("yes") or []
        no = ob.get("no") or []

    def last_price(arr):
        if arr and isinstance(arr[-1], (list, tuple)) and len(arr[-1]) >= 1:
            return arr[-1][0]
        return None

    yb = last_price(yes)
    nb = last_price(no)
    ya = (100 - nb) if nb is not None else None
    na = (100 - yb) if yb is not None else None
    return yb, ya, nb, na


def cents_as_dollars_str(x: Optional[int]) -> str:
    if x is None:
        return ""
    return f"${x/100:,.2f}"


# ---------- rendering ----------


def render_balance(bal: Dict[str, Any]) -> None:
    panel = Panel.fit(
        f"[bold]Cash:[/bold] {cents_to_dollars(bal.get('balance', 0))}  "
        f"[bold]Portfolio:[/bold] {cents_to_dollars(bal.get('portfolio_value', 0))}  "
        f"[bold]Updated:[/bold] {ts_to_iso(bal.get('updated_ts', 0))}",
        title="Account Balance",
        border_style="green",
    )
    console.print(panel)


def render_markets_with_prices(
    client: KalshiClient,
    markets: List[Dict[str, Any]],
    status: str,
    subtitle: str = "",
) -> None:
    table = Table(
        title=f"Markets (status={status}) {subtitle}".strip(),
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("Ticker", style="cyan", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("YES Bid", justify="right", style="green")
    table.add_column("YES Ask", justify="right", style="green")
    table.add_column("NO Bid", justify="right", style="red")
    table.add_column("NO Ask", justify="right", style="red")

    for m in markets:
        ticker = m.get("ticker", "")
        title = m.get("title", "")

        ob = fetch_orderbook(client, ticker)
        yb = ya = nb = na = None
        if ob:
            yb, ya, nb, na = parse_best_prices(ob)

        rstyle = ROW_STYLE[classify_market(m)]
        table.add_row(
            ticker,
            title,
            cents_as_dollars_str(yb),
            cents_as_dollars_str(ya),
            cents_as_dollars_str(nb),
            cents_as_dollars_str(na),
            style=rstyle,
        )

    console.print(table)


def render_orderbook(ob: Dict[str, Any], ticker: str) -> None:
    yb, ya, nb, na = parse_best_prices(ob)
    panel = Panel.fit(
        f"[bold]Ticker:[/bold] {ticker}\n"
        f"[bold]YES Bid:[/bold] {cents_as_dollars_str(yb)}\n"
        f"[bold]YES Ask:[/bold] {cents_as_dollars_str(ya)}\n"
        f"[bold]NO Bid:[/bold]  {cents_as_dollars_str(nb)}\n"
        f"[bold]NO Ask:[/bold]  {cents_as_dollars_str(na)}",
        title="Orderbook (best levels)",
        border_style="blue",
    )
    console.print(panel)


def render_positions(positions: List[Dict[str, Any]]) -> None:
    table = Table(title="Market Positions", box=box.SIMPLE_HEAVY)
    table.add_column("Ticker", style="cyan", no_wrap=True)
    table.add_column("Position", justify="right")
    table.add_column("Exposure", justify="right")
    table.add_column("Realized PnL", justify="right")
    table.add_column("Resting Orders", justify="right")
    table.add_column("Last Updated", style="dim")

    for p in positions:
        ticker = p.get("ticker", "")
        pos = str(p.get("position", 0))
        exposure = p.get("market_exposure_dollars") or cents_to_dollars(
            p.get("market_exposure", 0)
        )
        realized = p.get("realized_pnl_dollars") or cents_to_dollars(
            p.get("realized_pnl", 0)
        )
        resting = str(p.get("resting_orders_count", 0))
        last_updated = parse_iso8601(p.get("last_updated_ts"))

        style = ROW_STYLE[classify_market({"ticker": ticker, "title": ""})]
        table.add_row(ticker, pos, exposure, realized, resting, last_updated, style=style)

    console.print(table)


def render_orders(orders: List[Dict[str, Any]]) -> None:
    table = Table(title="Orders", box=box.SIMPLE_HEAVY)
    table.add_column("Order ID", style="cyan", no_wrap=True)
    table.add_column("Ticker", style="white")
    table.add_column("Side", justify="center")
    table.add_column("Action", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Price", justify="right")
    table.add_column("Remaining/Initial", justify="right")
    table.add_column("Created", style="dim")

    for o in orders:
        oid = o.get("order_id", "")
        ticker = o.get("ticker", "")
        side = o.get("side", "")
        action = o.get("action", "")
        status = o.get("status", "")

        price_cents = None
        if o.get("yes_price") is not None:
            price_cents = o.get("yes_price")
        elif o.get("no_price") is not None:
            price_cents = o.get("no_price")
        price = cents_as_dollars_str(price_cents) if price_cents is not None else ""

        remaining = o.get("remaining_count", 0)
        initial = o.get("initial_count", o.get("fill_count", 0) + remaining)
        rem_str = f"{remaining}/{initial}"

        created = parse_iso8601(o.get("created_time"))

        style = ROW_STYLE[classify_market({"ticker": ticker, "title": ""})]
        table.add_row(
            oid,
            ticker,
            str(side),
            str(action),
            str(status),
            price,
            rem_str,
            created,
            style=style,
        )

    console.print(table)


# ---------- command handlers ----------


def cmd_balance(client: KalshiClient, args: argparse.Namespace) -> None:
    bal = client.get_balance()
    if not bal:
        console.print("[red]Failed to fetch balance.[/red]")
        return
    if args.json:
        console.print_json(data=bal)
    else:
        render_balance(bal)


def cmd_markets(client: KalshiClient, args: argparse.Namespace) -> None:
    # Fetch markets (single page or all pages)
    if args.all:
        items = list(
            client.paginate(
                "/markets",
                limit=args.page_limit,
                params={"status": args.status},
                key="markets",
            )
        )
        markets = items
    else:
        raw = client.list_markets(status=args.status, limit=args.limit)
        markets = raw.get("markets", []) if raw else []

    # Filter by search term
    q = args.search.strip().lower() if args.search else ""
    if q:
        markets = [
            m
            for m in markets
            if q in (m.get("title", "").lower())
            or q in (m.get("ticker", "").lower())
        ]

    # Sort
    key = args.sort

    def keyfn(m: Dict[str, Any]):
        if key == "title":
            return m.get("title", "")
        if key == "ticker":
            return m.get("ticker", "")
        if key == "yes_price":
            return m.get("yes_price") if m.get("yes_price") is not None else -1
        if key == "no_price":
            return m.get("no_price") if m.get("no_price") is not None else -1
        return m.get("title", "")

    markets = sorted(markets, key=keyfn)

    # Save snapshot if requested
    if args.save:
        snap = {
            "fetched_at": ts_to_iso(int(time.time())),
            "status": args.status,
            "all": args.all,
            "page_limit": args.page_limit,
            "search": args.search,
            "sort": args.sort,
            "markets": markets,
        }
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2)
        console.print(f"[dim]Saved snapshot to {args.save}[/dim]")

    if args.json:
        console.print_json(data={"markets": markets})
    else:
        subtitle = ""
        if args.search or args.sort != "title":
            subtitle = f"(search='{args.search}', sort={args.sort})"
        console.print()
        render_markets_with_prices(client, markets, args.status, subtitle=subtitle)


def cmd_orderbook(client: KalshiClient, args: argparse.Namespace) -> None:
    ob = fetch_orderbook(client, args.ticker)
    if not ob:
        console.print(f"[red]Failed to fetch orderbook for {args.ticker}[/red]")
        return
    if args.json:
        console.print_json(data=ob)
    else:
        render_orderbook(ob, args.ticker)


def cmd_raw(client: KalshiClient, args: argparse.Namespace) -> None:
    data = client.request("GET", args.path)
    console.print(f"[dim]GET {args.path}[/dim]")
    console.print_json(data=data if data else {})


def cmd_positions(client: KalshiClient, args: argparse.Namespace) -> None:
    resp = client.get_positions(
        settlement_status=args.settlement_status,
        count_filter=args.count_filter,
        ticker=args.ticker,
        limit=args.limit,
    )
    if not resp:
        console.print("[red]Failed to fetch positions.[/red]")
        return

    if args.json:
        console.print_json(data=resp)
        return

    positions = resp.get("market_positions", [])
    if not positions:
        console.print("[yellow]No market positions found.[/yellow]")
        return

    render_positions(positions)


def cmd_orders(client: KalshiClient, args: argparse.Namespace) -> None:
    resp = client.get_orders(
        status=args.status,
        ticker=args.ticker,
        limit=args.limit,
    )
    if not resp:
        console.print("[red]Failed to fetch orders.[/red]")
        return

    if args.json:
        console.print_json(data=resp)
        return

    orders = resp.get("orders", [])
    if not orders:
        console.print("[yellow]No orders found for the given filters.[/yellow]")
        return

    render_orders(orders)

def cmd_cancel(client: KalshiClient, args: argparse.Namespace) -> None:
    """
    Cancel a single order by ID.
    """
    resp = client.cancel_order(args.order_id)
    if not resp:
        console.print(f"[red]Failed to cancel order {args.order_id}.[/red]")
        return

    if args.json:
        console.print_json(data=resp)
        return

    console.print(
        f"[green]Cancel request sent for order[/green] [bold]{args.order_id}[/bold]."
    )
    # If API returns status in resp, you could surface it here:
    status = resp.get("status") if isinstance(resp, dict) else None
    if status:
        console.print(f"[dim]New status: {status}[/dim]")


def cmd_cancel_all(client: KalshiClient, args: argparse.Namespace) -> None:
    """
    Cancel all orders for a given ticker (by status).
    """
    resp = client.cancel_all_for_ticker(
        ticker=args.ticker,
        status=args.status,
        limit=args.limit,
    )

    if resp is None:
        console.print(
            f"[red]Failed to fetch or cancel orders for ticker {args.ticker}.[/red]"
        )
        return

    if args.json:
        console.print_json(data=resp)
        return

    count = len(resp)
    console.print(
        f"[green]Sent cancel requests for {count} order(s)[/green] "
        f"on [bold]{args.ticker}[/bold] with status='{args.status}'."
    )
# ---------- trading: place orders ----------


def _place_order_from_args(client: KalshiClient, side: str, args: argparse.Namespace) -> None:

    yes_price = args.yes
    no_price = args.no

    # basic validation
    if yes_price is None and no_price is None:
        console.print("[red]You must provide either --yes or --no price.[/red]")
        return
    if yes_price is not None and no_price is not None:
        console.print("[red]Provide only one of --yes or --no, not both.[/red]")
        return

    if yes_price is not None and not (1 <= yes_price <= 99):
        console.print("[red]--yes price must be between 1 and 99 (cents).[/red]")
        return
    if no_price is not None and not (1 <= no_price <= 99):
        console.print("[red]--no price must be between 1 and 99 (cents).[/red]")
        return

    if args.qty <= 0:
        console.print("[red]--qty must be positive.[/red]")
        return

    body_yes = yes_price if yes_price is not None else None
    body_no = no_price if no_price is not None else None

    resp = client.place_order(
        ticker=args.ticker,
        side="yes" if yes_price is not None else "no",
        action=side,
        quantity=args.qty,
        yes_price=body_yes,
        no_price=body_no,
    )

    if not resp:
        console.print("[red]Order request failed (no response or HTTP error).[/red]")
        return

    if args.json:
        console.print_json(data=resp)
        return

    # Pretty print summary
    oid = resp.get("order_id")
    status = resp.get("status", "unknown")
    eff_yes = resp.get("yes_price")
    eff_no = resp.get("no_price")

    leg_str = ""
    if eff_yes is not None:
        leg_str = f"YES @ {eff_yes}¢"
    elif eff_no is not None:
        leg_str = f"NO @ {eff_no}¢"

    console.print(
        f"[green]Order sent:[/green] side=[bold]{side.upper()}[/bold], "
        f"ticker=[bold]{args.ticker}[/bold], qty=[bold]{args.qty}[/bold], {leg_str}"
    )
    if oid:
        console.print(f"[dim]Order ID: {oid} | Status: {status}[/dim]")


def cmd_order(client: KalshiClient, args: argparse.Namespace) -> None:
    """
    Generic order placement:
      kalshi order TICKER buy --yes 30 --qty 1
      kalshi order TICKER sell --no 70 --qty 2
    """
    _place_order_from_args(client, side=args.side, args=args)


def cmd_buy(client: KalshiClient, args: argparse.Namespace) -> None:
    """
    Buy YES or NO:
      kalshi buy TICKER --yes 30 --qty 1
      kalshi buy TICKER --no 70 --qty 2
    """
    _place_order_from_args(client, side="buy", args=args)


def cmd_sell(client: KalshiClient, args: argparse.Namespace) -> None:
    """
    Sell YES or NO:
      kalshi sell TICKER --yes 80 --qty 1
      kalshi sell TICKER --no 25 --qty 3
    """
    _place_order_from_args(client, side="sell", args=args)

# ---------- arg parsing ----------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kalshi demo client with subcommands."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # balance
    p_bal = subparsers.add_parser("balance", help="Show account balance")
    p_bal.add_argument("--json", action="store_true", help="Output raw JSON")
    p_bal.set_defaults(func=cmd_balance)

    # markets
    p_mk = subparsers.add_parser("markets", help="List markets")
    p_mk.add_argument(
        "--status", default="open", help="Market status filter (default: open)"
    )
    p_mk.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Number of markets (single page). Ignored with --all.",
    )
    p_mk.add_argument(
        "--all",
        action="store_true",
        help="Fetch all markets using pagination (ignores --limit).",
    )
    p_mk.add_argument(
        "--page-limit",
        type=int,
        default=100,
        help="Items per page when paginating (default: 100).",
    )
    p_mk.add_argument(
        "--search",
        default="",
        help="Substring filter over title/ticker (case-insensitive).",
    )
    p_mk.add_argument(
        "--sort",
        choices=["title", "ticker", "yes_price", "no_price"],
        default="title",
        help="Sort key for markets (metadata fields).",
    )
    p_mk.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted table.",
    )
    p_mk.add_argument(
        "--save",
        default="",
        help="If set, write markets JSON snapshot to this file.",
    )
    p_mk.set_defaults(func=cmd_markets)

    # orderbook
    p_ob = subparsers.add_parser(
        "orderbook", help="Show best bid/ask for a given ticker"
    )
    p_ob.add_argument("ticker", help="Market ticker, e.g. KXNBAGAME-...")
    p_ob.add_argument("--json", action="store_true", help="Output raw JSON")
    p_ob.set_defaults(func=cmd_orderbook)

    # positions
    p_pos = subparsers.add_parser("positions", help="Show market-level positions")
    p_pos.add_argument(
        "--settlement-status",
        choices=["unsettled", "settled", "all"],
        default="unsettled",
        help="Filter positions by settlement status (default: unsettled)",
    )
    p_pos.add_argument(
        "--count-filter",
        default="position",
        help='Count filter, e.g. "position", "total_traded", or "position,total_traded"',
    )
    p_pos.add_argument(
        "--ticker",
        default="",
        help="Filter positions by market ticker (optional)",
    )
    p_pos.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max records per page (API limit, default 100)",
    )
    p_pos.add_argument(
        "--json", action="store_true", help="Output raw JSON response"
    )
    p_pos.set_defaults(func=cmd_positions)

    # orders
    p_ord = subparsers.add_parser("orders", help="Show your orders")
    p_ord.add_argument(
        "--status",
        choices=["resting", "executed", "canceled", "all"],
        default="resting",
        help="Order status filter (default: resting = open orders)",
    )
    p_ord.add_argument(
        "--ticker",
        default="",
        help="Filter orders by market ticker (optional)",
    )
    p_ord.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max records per page (API limit, default 100)",
    )
    p_ord.add_argument(
        "--json", action="store_true", help="Output raw JSON response"
    )
    p_ord.set_defaults(func=cmd_orders)

        # cancel (single order)
    p_cancel = subparsers.add_parser(
        "cancel", help="Cancel a single order by ID"
    )
    p_cancel.add_argument(
        "order_id",
        help="Order ID to cancel (use 'kalshi orders' to list IDs)",
    )
    p_cancel.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response",
    )
    p_cancel.set_defaults(func=cmd_cancel)

    # cancel-all (all orders for a ticker)
    p_calla = subparsers.add_parser(
        "cancel-all", help="Cancel all orders for a given ticker"
    )
    p_calla.add_argument(
        "ticker",
        help="Market ticker whose orders should be cancelled",
    )
    p_calla.add_argument(
        "--status",
        choices=["resting", "executed", "canceled", "all"],
        default="resting",
        help="Which orders to cancel (default: resting = open orders only)",
    )
    p_calla.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Max number of orders to cancel in one run (safety cap)",
    )
    p_calla.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON list of cancel responses",
    )
    p_calla.set_defaults(func=cmd_cancel_all)

        # order (generic)
    p_ord_place = subparsers.add_parser(
        "order",
        help="Place a generic order (buy/sell YES or NO)",
    )
    p_ord_place.add_argument(
        "ticker",
        help="Market ticker, e.g. KXNBAGAME-25NOV14BKNORL-ORL",
    )
    p_ord_place.add_argument(
        "side",
        choices=["buy", "sell"],
        help="Side of the contract (buy or sell)",
    )
    p_ord_place.add_argument(
        "--yes",
        type=int,
        default=None,
        help="YES price in cents (1–99). Provide either --yes or --no.",
    )
    p_ord_place.add_argument(
        "--no",
        type=int,
        default=None,
        help="NO price in cents (1–99). Provide either --yes or --no.",
    )
    p_ord_place.add_argument(
        "--qty",
        type=int,
        default=1,
        help="Number of contracts to trade (default: 1).",
    )
    p_ord_place.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response.",
    )
    p_ord_place.set_defaults(func=cmd_order)

    # buy (convenience: side=buy)
    p_buy = subparsers.add_parser(
        "buy",
        help="Buy YES or NO on a given market",
    )
    p_buy.add_argument(
        "ticker",
        help="Market ticker, e.g. KXNBAGAME-25NOV14BKNORL-ORL",
    )
    p_buy.add_argument(
        "--yes",
        type=int,
        default=None,
        help="YES price in cents (1–99). Provide either --yes or --no.",
    )
    p_buy.add_argument(
        "--no",
        type=int,
        default=None,
        help="NO price in cents (1–99). Provide either --yes or --no.",
    )
    p_buy.add_argument(
        "--qty",
        type=int,
        default=1,
        help="Number of contracts to trade (default: 1).",
    )
    p_buy.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response.",
    )
    p_buy.set_defaults(func=cmd_buy)

    # sell (convenience: side=sell)
    p_sell = subparsers.add_parser(
        "sell",
        help="Sell YES or NO on a given market",
    )
    p_sell.add_argument(
        "ticker",
        help="Market ticker, e.g. KXNBAGAME-25NOV14BKNORL-ORL",
    )
    p_sell.add_argument(
        "--yes",
        type=int,
        default=None,
        help="YES price in cents (1–99). Provide either --yes or --no.",
    )
    p_sell.add_argument(
        "--no",
        type=int,
        default=None,
        help="NO price in cents (1–99). Provide either --yes or --no.",
    )
    p_sell.add_argument(
        "--qty",
        type=int,
        default=1,
        help="Number of contracts to trade (default: 1).",
    )
    p_sell.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response.",
    )
    p_sell.set_defaults(func=cmd_sell)


    # raw (debug)
    p_raw = subparsers.add_parser(
        "raw", help="GET an arbitrary API path for debugging"
    )
    p_raw.add_argument(
        "path",
        help="API path, e.g. /markets or /markets/<ticker>/orderbook (without base URL)",
    )
    p_raw.set_defaults(func=cmd_raw)

    return parser


# ---------- main ----------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    client = KalshiClient(
        api_key_id=config.API_KEY_ID,
        private_key_path=config.PRIVATE_KEY_PATH,
        base_url=config.BASE_URL,
    )

    console.rule("[bold green]Kalshi Bot CLI[/bold green]")
    args.func(client, args)


if __name__ == "__main__":
    main()
