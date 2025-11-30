import time
import json
import base64
import requests
from typing import Optional, Dict, Any, Iterable, List
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
import logging

logger = logging.getLogger("kalshi")
logger.setLevel(logging.INFO)


# Kalshi trade API base path (used in signing and URLs)
API_BASE_PATH = "/trade-api/v2"


class KalshiClient:
    def __init__(self, api_key_id: str, private_key_path: str, base_url: str):

        self.api_key_id = api_key_id
        self.base_url = base_url.rstrip("/")
        self.private_key = self._load_private_key(private_key_path)

    # ---------- key loading & signing ----------

    @staticmethod
    def _load_private_key(path: str):
        with open(path, "rb") as f:
            data = f.read()
        return serialization.load_pem_private_key(data, password=None)

    def _create_signature(self, timestamp_ms: str, method: str, path: str) -> str:

        full_path = f"{API_BASE_PATH}{path}"
        path_without_query = full_path.split("?", 1)[0]

        message = f"{timestamp_ms}{method}{path_without_query}".encode("utf-8")

        signature = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _build_query(self, params: Dict[str, Any]) -> str:

        parts: List[str] = []
        for k, v in params.items():
            if v is None or v == "":
                continue
            parts.append(f"{k}={v}")
        return "&".join(parts)

    def _build_url(self, path: str) -> str:
       
        if self.base_url.endswith(API_BASE_PATH):
            return f"{self.base_url}{path}"
        return f"{self.base_url}{API_BASE_PATH}{path}"

    # ---------- core request ----------

    def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        
        # ---------- Core authenticated request helper ----------
        method = method.upper()
        ts_ms = str(int(time.time() * 1000))

        signature = self._create_signature(ts_ms, method, path)

        headers = {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "Content-Type": "application/json",
        }

        url = self._build_url(path)

        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=10)
            elif method in ("POST", "PUT", "PATCH"):
                resp = requests.request(
                    method, url, headers=headers, data=json.dumps(data or {}), timeout=10
                )
            elif method == "DELETE":
                if data:
                    resp = requests.delete(
                        url, headers=headers, data=json.dumps(data), timeout=10
                    )
                else:
                    resp = requests.delete(url, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except requests.RequestException as e:
            print(f"Request error: {e}")
            return None

            if not (200 <= resp.status_code < 300):
                logger.error(
                 f"[HTTP ERROR] {method} {path} | Status {resp.status_code} | Response: {resp.text}"
    )
            return None

        try:
            return resp.json()
        except json.JSONDecodeError:
            print("Warning: response was not valid JSON")
            return None

    # ---------- pagination helper ----------

    def kalpaginate(
        self,
        base_path: str,
        limit: int,
        params: Optional[Dict[str, Any]],
        key: str,
    ) -> Iterable[Dict[str, Any]]:
        
    # ---------- Generic cursor-based pagination helper ----------
        
        cursor: Optional[str] = None

        while True:
            q: Dict[str, Any] = dict(params or {})
            q["limit"] = limit
            if cursor:
                q["cursor"] = cursor

            qs = self._build_query(q)
            path = base_path if not qs else f"{base_path}?{qs}"

            resp = self.request("GET", path)
            if not resp:
                break

            items = resp.get(key, [])
            for item in items:
                yield item

            cursor = resp.get("cursor")
            if not cursor:
                break

    # ---------- basic high-level helpers ----------

    def get_balance(self) -> Optional[Dict[str, Any]]:
        return self.request("GET", "/portfolio/balance")

    def list_markets(
        self,
        status: str = "open",
        limit: int = 15,
    ) -> Optional[Dict[str, Any]]:
        params = {"status": status, "limit": limit}
        qs = self._build_query(params)
        path = "/markets" if not qs else f"/markets?{qs}"
        return self.request("GET", path)

    def place_order(
        self,
        ticker: str,
        side: str, #yes/no
        action: str, #buy/sell
        quantity: int,
        yes_price: Optional[int] = None,
        no_price: Optional[int] = None,
        order_type: str = "limit",
       # time_in_force: str = "gtc",
    ) -> Optional[Dict[str, Any]]:
        body: Dict[str, Any] = {
            "ticker": ticker,
            "action": action,
            "type": order_type,
           # "time_in_force": time_in_force,
            "side": side,
            "count": quantity,
        }
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price

        return self.request("POST", "/portfolio/orders", data=body)

    # ---------- portfolio: positions & orders ----------

    def get_positions(
        self,
        settlement_status: str = "unsettled",
        count_filter: str = "position",
        ticker: Optional[str] = None,
        event_ticker: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "limit": limit,
            "settlement_status": settlement_status,
            "count_filter": count_filter,
        }
        if ticker:
            params["ticker"] = ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        if cursor:
            params["cursor"] = cursor

        qs = self._build_query(params)
        path = "/portfolio/positions" if not qs else f"/portfolio/positions?{qs}"
        return self.request("GET", path)

    def get_orders(
        self,
        status: str = "resting",
        ticker: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
       
        params: Dict[str, Any] = {
            "limit": limit,
        }
        if status and status != "all":
            params["status"] = status
        if ticker:
            params["ticker"] = ticker
        if cursor:
            params["cursor"] = cursor

        qs = self._build_query(params)
        path = "/portfolio/orders" if not qs else f"/portfolio/orders?{qs}"
        return self.request("GET", path)

    def cancel_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        return self.request("DELETE", f"/portfolio/orders/{order_id}")

    def cancel_all_for_ticker(
        self,
        ticker: str,
        status: str = "resting",
        limit: int = 1000,
    ) -> Optional[List[Dict[str, Any]]]:
        
        resp = self.get_orders(status=status, ticker=ticker, limit=limit)
        if not resp or "orders" not in resp:
            return None

        results: List[Dict[str, Any]] = []
        for order in resp["orders"]:
            oid = order.get("order_id")
            if not oid:
                continue
            cancelled = self.cancel_order(oid)
            if cancelled is not None:
                results.append(cancelled)
        return results
