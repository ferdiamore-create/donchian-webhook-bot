from flask import Flask, request, jsonify
import os
import requests
import math

app = Flask(__name__)

ALPACA_KEY = os.environ.get("ALPACA_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET")
ALPACA_URL = "https://paper-api.alpaca.markets"
TRADE_EUR = float(os.environ.get("TRADE_EUR", "1000"))
BOT_CAPITAL_EUR = 10000


@app.route("/", methods=["GET"])
def home():
    return "Donchian Webhook Bot is running", 200


@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    action = str(data.get("action", "")).upper()
    ticker = str(data.get("ticker", "")).upper().strip()

    if action not in ["BUY", "SELL"]:
        return jsonify({"error": "Invalid action"}), 400

    if not ticker:
        return jsonify({"error": "Missing ticker"}), 400

    if not ALPACA_KEY or not ALPACA_SECRET:
        return jsonify({"error": "Alpaca credentials not configured"}), 500

    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
        "Content-Type": "application/json"
    }
# =====================================================
    # LIMITE CAPITALE BOT
    # =====================================================

    if action == "BUY":

        positions_url = f"{ALPACA_URL}/v2/positions"

        positions_response = requests.get(
            positions_url,
            headers=headers,
            timeout=3
        )

        if positions_response.status_code != 200:
            return jsonify({
                "error": "Could not get positions",
                "details": positions_response.text
            }), 500

        positions = positions_response.json()

        capitale_usato_usd = sum(
            float(p.get("market_value", 0))
            for p in positions
            if float(p.get("qty", 0)) > 0
        )

        capitale_massimo_usd = BOT_CAPITAL_EUR * 1.17
        prossima_operazione_usd = TRADE_EUR * 1.17

        if capitale_usato_usd + prossima_operazione_usd > capitale_massimo_usd:

            return jsonify({
                "status": "BUY BLOCCATO - LIMITE CAPITALE RAGGIUNTO",
                "capitale_usato_usd": capitale_usato_usd,
                "limite_usd": capitale_massimo_usd
            }), 200

    

        # Get current stock price
        quote_url = f"{ALPACA_URL}/v2/stocks/{ticker}/quotes/latest"

        quote_response = requests.get(
            quote_url,
            headers=headers,
            timeout=3
        )

        if quote_response.status_code != 200:
            return jsonify({
                "error": "Could not get stock price",
                "details": quote_response.text
            }), 500

        quote = quote_response.json()
        ask_price = quote["quote"]["ap"]

        if not ask_price or ask_price <= 0:
            return jsonify({"error": "Invalid stock price"}), 500

        qty = math.floor((TRADE_EUR * 1.17) / ask_price)

        if qty < 1:
            return jsonify({
                "error": "Trade amount too small for this stock"
            }), 400

        order = {
            "symbol": ticker,
            "qty": qty,
            "side": "buy",
            "type": "market",
            "time_in_force": "day"
        }

    else:

        # Close the entire position
        order = {
            "symbol": ticker,
            "qty": 0,
            "side": "sell",
            "type": "market",
            "time_in_force": "day"
        }

        # Get current position to determine quantity
        position_url = f"{ALPACA_URL}/v2/positions/{ticker}"

        position_response = requests.get(
            position_url,
            headers=headers,
            timeout=3
        )

        if position_response.status_code == 404:
            return jsonify({
                "status": "No position to sell",
                "ticker": ticker
            }), 200

        if position_response.status_code != 200:
            return jsonify({
                "error": "Could not get position",
                "details": position_response.text
            }), 500

        position = position_response.json()
        qty = position.get("qty")

        if not qty or float(qty) <= 0:
            return jsonify({
                "status": "No position to sell",
                "ticker": ticker
            }), 200

        order["qty"] = qty

    order_url = f"{ALPACA_URL}/v2/orders"

    response = requests.post(
        order_url,
        headers=headers,
        json=order,
        timeout=3
    )

    if response.status_code not in [200, 201]:
        return jsonify({
            "error": "Alpaca order rejected",
            "details": response.text
        }), 500

    return jsonify({
        "status": "ORDER SENT",
        "action": action,
        "ticker": ticker,
        "order": response.json()
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
