from flask import Flask, request, jsonify
import stripe
import os
from dotenv import load_dotenv
import pymysql
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
CORS(app)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Helper to connect to MySQL
def get_db_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306)),  # Add port, default to 3306
        cursorclass=pymysql.cursors.DictCursor
    )

@app.route("/create-payment-intent", methods=["POST"])
def create_payment():
    try:
        data = request.json
        amount = data.get("amount")
        if not amount:
            return jsonify({"error": "Amount is required"}), 400
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            payment_method_types=["card"]
        )
        return jsonify({"clientSecret": intent.client_secret})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        data = request.json
        amount = data.get("amount")
        if not amount:
            return jsonify({"error": "Amount is required"}), 400
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Your Product Name"},
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url="http://localhost:8000/success.html",
            cancel_url="http://localhost:8000/cancel.html",
        )
        return jsonify({"id": session.id, "url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400
    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO payments 
                    (id, amount, currency, status) 
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    intent['id'],
                    intent['amount'],
                    intent['currency'],
                    intent['status']
                ))
            conn.commit()
        except Exception as db_error:
            print("Error inserting into DB:", db_error)
        finally:
            if conn:
                conn.close()
    return "", 200

if __name__ == "__main__":
    app.run(port=5000)
