# -*- coding: utf-8 -*-
"""
OKX 持倉變化監控推播系統 - 支援 Discord 多 Webhook
作者：ChatGPT 為 蔡定緯 製作
"""

import os, time, threading, requests
from datetime import datetime, timezone
from flask import Flask

# ✅ 多組 Discord Webhook，可切換用來分流避免 429
WEBHOOKS = [
    "https://discord.com/api/webhooks/1394402678079094794/lfoAz17vpmW6ZuCtdtSxG7CoNzuujOCyB2tWyQ9oraHLI_olDHO5JwgG9kVnCK70hQUn",
    "https://discord.com/api/webhooks/1394403286748102787/HJTZ5Rx2U3NEJOhAhpvFY5k0ynQvh6WpnW9C-R8MN--RKHtYjpA_imjLZ4zPfS-nua6m",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "OK-ACCESS-KEY": "",         # 如果你使用私有 API，需要填入金鑰
    "OK-ACCESS-SIGN": "",
    "OK-ACCESS-TIMESTAMP": "",
    "OK-ACCESS-PASSPHRASE": ""
}

INTERVAL_SEC = 180  # 每 3 分鐘掃描一次
prev_oi = {}
pos_streak, neg_streak = {}, {}

# === OKX 永續合約 API ===
def fetch_okx_symbols():
    try:
        r = requests.get("https://www.okx.com/api/v5/public/instruments?instType=SWAP", timeout=10)
        data = r.json()["data"]
        return [i["instId"] for i in data if i["ctType"] == "linear" and i["instId"].endswith("-USDT-SWAP")]
    except Exception as e:
        print("⚠️ 無法取得 OKX 幣種列表：", e)
        return []

def fetch_oi(inst_id):
    try:
        url = f"https://www.okx.com/api/v5/public/open-interest?instId={inst_id}"
        r = requests.get(url, timeout=10)
        data = r.json()["data"]
        return float(data[0]["oiCcy"]) if data else None
    except Exception as e:
        print(f"⚠️ 無法取得 OI: {inst_id}", e)
        return None

# === Discord 推播 ===
webhook_index = 0
def push(msg):
    global webhook_index
    for _ in range(len(WEBHOOKS)):
        webhook_url = WEBHOOKS[webhook_index]
        webhook_index = (webhook_index + 1) % len(WEBHOOKS)
        try:
            r = requests.post(webhook_url, json={"content": f"```{msg}```"}, timeout=10)
            print(f"📨 webhook status: {r.status_code}")
            if r.status_code == 204:
                return
        except Exception as e:
            print("❌ webhook 發送錯誤：", e)
    print("🚫 全部 webhook 發送失敗")

# === 主邏輯 ===
def monitor_loop():
    while True:
        symbols = fetch_okx_symbols()[:50]
        print("🪪 幣種數量：", len(symbols))

        snap, diff_pct = {}, {}
        for s in symbols:
            val = fetch_oi(s)
            if val is None:
                continue
            snap[s] = val
            if s in prev_oi:
                pct = (val - prev_oi[s]) / prev_oi[s] * 100
                diff_pct[s] = pct
                if pct > 0:
                    pos_streak[s] = pos_streak.get(s, 0) + 1
                    neg_streak[s] = 0
                elif pct < 0:
                    neg_streak[s] = neg_streak.get(s, 0) + 1
                    pos_streak[s] = 0
            prev_oi[s] = val

        print("📊 有效 OI 幣種數：", len(snap))
        if snap:
            top_pos = sorted(((s, p) for s, p in diff_pct.items() if p > 0), key=lambda x: x[1], reverse=True)[:10]
            top_neg = sorted(((s, p) for s, p in diff_pct.items() if p < 0), key=lambda x: x[1])[:10]
            biggest5 = sorted(snap.items(), key=lambda x: x[1], reverse=True)[:5]

            ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            lines = [f"🌀 OKX 持倉變化量排名（{ts}）"]
            for sym, val in biggest5:
                d = diff_pct.get(sym, 0)
                lines.append(f"{sym}: 持倉量: {val:,.2f} USDT | 變化: {d:+.2f}%")
            lines += ["", "📈 正成長前十："]
            for sym, d in top_pos:
                lines.append(f"{sym:<15} | 持倉: {snap[sym]:,.2f} | 漲幅: {d:+.2f}% | 連續+: {pos_streak.get(sym, 0)}")
            lines += ["", "📉 負成長前十："]
            for sym, d in top_neg:
                lines.append(f"{sym:<15} | 持倉: {snap[sym]:,.2f} | 跌幅: {d:+.2f}% | 連續-: {neg_streak.get(sym, 0)}")

            push("\n".join(lines))

        time.sleep(INTERVAL_SEC)

# === Flask App for Keep-Alive ===
app = Flask(__name__)

@app.route("/healthz")
def healthz():
    return "ok", 200

if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
