import time
import json
import base64
import requests
from typing import Optional, Dict, Any, Iterable
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

API_BASE_PATH = "/trade-api/v2"

class KalshiClient:
    def __init__(self, api_key_id: str, private_key_path: str, base_url: str):
        self.api_key_id = api_key_id
        self.private_key_path = private_key_path
        self.base_url = base_url.rstrip("/")
        self.private_key = self._load_private_key_from_file()
        self.session = requests.Session()

    # ---------- internals ----------
    def _load_private_key_from_file(self):
        with open(self.private_key_path, "rb") as key_file:
            return serialization.load_pem_private_key(key_file.read(), password=None)

    def _ts_ms(self) -> str:
        return str(int(time.time_ns() // 1_000_000))

    def _sign_pss(self, timestamp_ms: str, method: str, path_with_query: str) -> str:
        # sign full API path, strip query
        if path_with_query.startswith(API_BASE_PATH):
            signed_path = path_with_query.split("?", 1)[0]
        else:
            signed_path = (API_BASE_PATH + path_with_query).split("?", 1)[0]
        text = timestamp_ms + method + signed_path
        sig = self.private_key.sign(
            text.encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode("utf-8")

    def _headers(self, ts_ms: str, signature_b64: str) -> Dict[str, str]:
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,      # milliseconds
            "KALSHI-ACCESS-SIGNATURE": signature_b64,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        if self.base_url.endswith(API_BASE_PATH):
            return self.base_url + (path if path.startswith("/") else "/" + path)
        if path.startswith(API_BASE_PATH):
            return self.base_url + path
        return self.base_url + API_BASE_PATH + (path if path.startswith("/") else "/" + path)

    def _request_once(self, method: str, path: str, data: Optional[dict]) -> Optional[requests.Response]:
        ts_ms = self._ts_ms()
        sig = self._sign_pss(ts_ms, method, path)
        headers = self._headers(ts_ms, sig)
        url = self._url(path)
        body = None if (method == "GET" or data is None) else json.dumps(data).encode("utf-8")
        try:
            if method == "GET":
                return self.session.get(url, headers=headers)
            if method == "POST":
                return self.session.post(url, headers=headers, data=body)
            raise ValueError(f"Unsupported method: {method}")
        except requests.RequestException:
            return None

    # ---------- robust request (rate limits, retries) ----------
    def request(self, method: str, path: str, data: Optional[dict] = None) -> Optional[dict]:
        max_retries = 5
        base_sleep = 0.25
        for attempt in range(max_retries):
            resp = self._request_once(method, path, data)
            if resp is None:
                time.sleep(base_sleep * (2 ** attempt))
                continue
            if resp.status_code == 401:
                # bad signature/creds; do not retry
                try:
                    resp.raise_for_status()
                except requests.HTTPError:
                    pass
                return None
            if resp.status_code in (429, 500, 502, 503, 504):
                # rate-limit/backoff
                ra = resp.headers.get("Retry-After")
                if ra:
                    try:
                        time.sleep(float(ra))
                    except ValueError:
                        time.sleep(base_sleep * (2 ** attempt))
                else:
                    time.sleep(base_sleep * (2 ** attempt))
                continue
            try:
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError:
                # non-retryable error
                return None
        return None

    # ---------- pagination ----------
    def paginate(self, path: str, *, limit: int = 100, params: Dict[str, Any] | None = None, key: str = "") -> Iterable[Any]:
        """
        Cursor-based pagination. If key provided, yields each item under response[key].
        Otherwise yields each page dict.
        """
        params = dict(params or {})
        params["limit"] = limit
        cursor = None
        while True:
            qs = "&".join([f"{k}={params[k]}" for k in params if params[k] is not None])
            url_path = f"{path}?{qs}" if qs else path
            if cursor:
                url_path += f"&cursor={cursor}"
            data = self.request("GET", url_path)
            if not data:
                return
            if key:
                for item in data.get(key, []):
                    yield item
            else:
                yield data
            cursor = data.get("cursor")
            if not cursor:
                break

    # ---------- convenience ----------
    def get_balance(self) -> Optional[Dict[str, Any]]:
        return self.request("GET", "/portfolio/balance")

    def list_markets(self, *, status: str = "open", limit: int = 10) -> Optional[Dict[str, Any]]:
        # standard single-page helper
        path_no_query = "/markets"
        url_path_with_query = f"{path_no_query}?status={status}&limit={limit}"
        return self.request("GET", url_path_with_query)

    def place_order(self, *, ticker: str, side: str, quantity: int, yes_price: Optional[int] = None, no_price: Optional[int] = None) -> Optional[Dict[str, Any]]:
        order = {"ticker": ticker, "side": side, "quantity": quantity}
        if yes_price is not None:
            order["yes_price"] = yes_price
        if no_price is not None:
            order["no_price"] = no_price
        return self.request("POST", "/orders", data=order)
