# Kalshi Demo Trading Client

A fully functional Python client and command-line interface (CLI) for the **Kalshi Demo API**, built to authenticate using RSA-PSS signatures and interact with markets, portfolios, and orders.

This project demonstrates complete API integration with features such as pagination, rate-limit handling, formatted console output, and environment-based configuration.

---

## 📦 Features

- **RSA-PSS Authentication** — Securely signs all requests per Kalshi API spec.  
- **Environment-based Configuration** — Credentials and keys stored locally in `.env` (never committed).  
- **Rate-Limit & Retry Logic** — Handles `429` and `5xx` responses automatically.  
- **Pagination Support** — Seamlessly fetches all markets using cursor-based pagination.  
- **Market Order Book Display** — Fetches bids/asks and computes implied prices.  
- **Rich Console UI** — Beautifully formatted tables using the `rich` library.  
- **Filtering & Sorting** — Filter markets by title, ticker, or price; sort by metadata.  
- **Data Export** — Save fetched markets as JSON snapshots.  
- **Automatic Refresh** — Optionally poll markets at defined intervals.  
- **Secure Secrets Management** — `.env` and `.pem` excluded via `.gitignore`.

---

## 🧠 Project Structure

kalshi_bot/
├── main.py # Command-line entrypoint and console UI
├── kalshi_client.py # API client with signing, pagination, and rate-limit logic
├── config.py # Loads credentials and environment variables
├── .env # Local API key and private key path (not tracked)
├── .gitignore # Ignores sensitive and generated files
└── privateRSA.pem # RSA private key (local only)


---

## ⚙️ Setup & Installation

1️⃣ Clone this repository
```bash
git clone git@github.com:gurtejsingh7/kalshibot.git
cd kalshibot
```

2️⃣ Create and activate a virtual environment
```python -m venv .venv
.\.venv\Scripts\activate
```
3️⃣ Install dependencies
```pip install -r requirements.txt
```
4️⃣ Add your environment variables
```
Create a .env file in the project root:

BASE_URL=https://demo-api.kalshi.co/trade-api/v2
API_KEY_ID=<your-demo-api-key-id>
PRIVATE_KEY_PATH=C:\Users\<user>\Documents\kalshi_bot\privateRSA.pem
```
5️⃣ Run the client
```python main.py
```
💻 CLI Options
| Option                       | Description                                    |           |           |              |
| ---------------------------- | ---------------------------------------------- | --------- | --------- | ------------ |
| `--status open/closed`       | Filter markets by status                       |           |           |              |
| `--limit N`                  | Limit the number of results                    |           |           |              |
| `--all --page-limit N`       | Fetch all markets via pagination               |           |           |              |
| `--search "keyword"`         | Filter by title or ticker                      |           |           |              |
| `--sort title                | ticker                                         | yes_price | no_price` | Sort results |
| `--json`                     | Output raw JSON instead of formatted tables    |           |           |              |
| `--save filename.json`       | Save output to a file                          |           |           |              |
| `--debug-ticker TICKER`      | Inspect a single market’s orderbook            |           |           |              |
| `--debug-path /path`         | Call an arbitrary API endpoint                 |           |           |              |
| `--refresh X --iterations Y` | Auto-refresh data every X seconds for Y cycles |           |           |              |


Example:
```
python main.py --status open --limit 15 --search "NBA"
```
🧾 Example Output
--- Kalshi Bot ---
 Account Balance
 Cash: $2,450.00  Portfolio: $0.00  Updated: 2025-11-12 16:07:23 UTC

 Markets (status=open, limit=15)
 ─────────────────────────────────────────────
 Ticker                        Title                          YES Bid  YES Ask  NO Bid  NO Ask
 KXNCAAMBGAME-25NOV14LEHRUTG-LEH  Lehigh at Rutgers Winner?    $0.45    $0.55    $0.45   $0.55
 ...


🛠️ Tech Stack

-Python 3.11+
-requests — for HTTP communication
-cryptography — for RSA-PSS signing
-python-dotenv — to load environment variables

rich — for console formatting

📜 Example requirements.txt
```
requests>=2.31.0
cryptography>=42.0.5
python-dotenv>=1.0.1
rich>=13.6.0
```
⚠️ Notes

The Demo Environment does not show real liquidity; many markets will have empty order books.
For production, replace the BASE_URL and keypair in .env.
The client already handles Kalshi’s published rate limits (20 reads/s, 10 writes/s).
Supports sub-penny and dollar-string fields introduced in 2025 API update.

🔒 Security

.env, .pem, and .venv/ are excluded from Git.
RSA keys and API credentials remain local.
No credentials are printed or logged.
Safe for open-source distribution.

👤 Author

Gurtej Singh
github.com/gurtejsingh7

🧩 License

MIT License © 2025 Gurtej Singh
Feel free to use, modify, or extend for educational and non-commercial purposes.
