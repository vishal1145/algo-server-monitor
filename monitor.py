"""
Website Monitor — GitHub Actions version
State is persisted via a local state.json file (cached between runs by GitHub Actions).
"""

import json
import os
import time
import datetime
import requests

# ─── CONFIG ───────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Multiple chat IDs supported — comma separated in env var
# e.g. TELEGRAM_CHAT_IDS = "7594589413,987654321"
_ids_env = os.environ.get("TELEGRAM_CHAT_IDS", os.environ.get("TELEGRAM_CHAT_ID", ""))
TELEGRAM_CHAT_IDS = [cid.strip() for cid in _ids_env.split(",") if cid.strip()]

WEBSITES = [
    "https://algofolks.com/",
    "https://igas-energy.de/",
]

REQUEST_TIMEOUT        = 10
SLOW_THRESHOLD_SECONDS = 3.0
STATE_FILE             = "state.json"
# ──────────────────────────────────────────────────


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN:
        print("[TELEGRAM] Token not set.")
        return
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10)
            if resp.ok:
                print(f"[TELEGRAM] Sent to {chat_id}: {message[:60]}...")
            else:
                print(f"[TELEGRAM ERROR] {chat_id} → {resp.status_code} - {resp.json().get('description')}")
        except Exception as e:
            print(f"[TELEGRAM ERROR] {chat_id} → {e}")


def check_site(url: str) -> dict:
    result = {"url": url, "status": "UNKNOWN", "code": None, "response_time": None, "error": None}
    try:
        start = time.time()
        resp  = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True,
                             headers={"User-Agent": "SiteMonitor/1.0"})
        elapsed = round(time.time() - start, 2)
        result["code"]          = resp.status_code
        result["response_time"] = elapsed
        if resp.status_code < 400:
            result["status"] = "SLOW" if elapsed > SLOW_THRESHOLD_SECONDS else "UP"
        else:
            result["status"] = "DOWN"
    except requests.exceptions.ConnectionError:
        result["status"] = "DOWN"
        result["error"]  = "Connection refused / DNS failed"
    except requests.exceptions.Timeout:
        result["status"] = "DOWN"
        result["error"]  = f"Timed out after {REQUEST_TIMEOUT}s"
    except requests.exceptions.SSLError:
        result["status"] = "DOWN"
        result["error"]  = "SSL certificate error"
    except Exception as e:
        result["status"] = "DOWN"
        result["error"]  = str(e)
    return result


def main():
    state = load_state()
    now   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] Checking {len(WEBSITES)} site(s)...\n")

    for url in WEBSITES:
        r    = check_site(url)
        prev = state.get(url, {}).get("status")

        code_str = f" (HTTP {r['code']})" if r["code"] else ""
        time_str = f"\nResponse: {r['response_time']}s" if r["response_time"] else ""
        err_str  = f"\nReason: {r['error']}" if r["error"] else ""

        print(f"  {'✅' if r['status'] == 'UP' else '⚠️' if r['status'] == 'SLOW' else '❌'} "
              f"{r['status']:6}  {url}  {r['response_time'] or ''}s")

        # Alert only on status change
        if prev != r["status"]:
            if r["status"] == "DOWN":
                send_telegram(
                    f"🚨 <b>SITE DOWN</b>\n"
                    f"URL: {url}{code_str}\n"
                    f"Time: {now}{err_str}"
                )
            elif r["status"] in ("UP", "SLOW") and prev == "DOWN":
                send_telegram(
                    f"✅ <b>SITE RECOVERED</b>\n"
                    f"URL: {url}{code_str}\n"
                    f"Time: {now}{time_str}"
                )
            elif r["status"] == "SLOW" and prev == "UP":
                send_telegram(
                    f"⚠️ <b>SITE SLOW</b>\n"
                    f"URL: {url}{code_str}\n"
                    f"Time: {now}{time_str}"
                )

        # Update state
        state[url] = {
            "status":        r["status"],
            "code":          r["code"],
            "response_time": r["response_time"],
            "last_checked":  now,
        }

    save_state(state)
    print("\nDone. State saved.")


if __name__ == "__main__":
    main()
