import hmac
import os
import re
import sqlite3
import time
from datetime import datetime

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for)

app = Flask(__name__)
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "bank.db"))

# ---------- admin login settings ----------
# Set these as environment variables (on Render: Environment tab).
# Local testing falls back to admin / admin123. That fallback is blocked on Render.
ON_RENDER = bool(os.environ.get("RENDER"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "" if ON_RENDER else "admin123")
if not ADMIN_PASSWORD:
    raise RuntimeError("Set the ADMIN_PASSWORD environment variable before deploying.")

app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=ON_RENDER,  # cookie only over https on Render
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,  # stay logged in for 8 hours
)

# very small brute-force protection: 5 wrong tries -> locked for 5 minutes (per IP)
MAX_TRIES = 5
LOCK_SECONDS = 300
failed = {}  # ip -> [count, first_fail_time]

MIN_BALANCE = {"S": 500, "C": 1000}  # Saving >= 500, Current >= 1000
TYPE_NAME = {"S": "Saving", "C": "Current"}


# ---------- database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            acc_no  TEXT PRIMARY KEY,
            name    TEXT NOT NULL,
            type    TEXT NOT NULL CHECK (type IN ('S','C')),
            balance REAL NOT NULL,
            created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            acc_no  TEXT NOT NULL,
            kind    TEXT NOT NULL,
            amount  REAL NOT NULL,
            balance REAL NOT NULL,
            at      TEXT NOT NULL
        );
        """
    )
    db.commit()
    db.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_tx(db, acc_no, kind, amount, balance):
    db.execute(
        "INSERT INTO transactions (acc_no, kind, amount, balance, at) VALUES (?,?,?,?,?)",
        (acc_no, kind, amount, balance, now()),
    )


def account_dict(row):
    d = dict(row)
    d["type_name"] = TYPE_NAME[d["type"]]
    d["min_balance"] = MIN_BALANCE[d["type"]]
    return d


def error(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


def parse_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if amount <= 0 or amount != amount or amount > 1e9:
        return None
    return round(amount, 2)


def find(db, acc_no):
    return db.execute("SELECT * FROM accounts WHERE acc_no = ?", (acc_no,)).fetchone()


# ---------- login / logout ----------
def client_ip():
    # Render puts the real visitor address in X-Forwarded-For
    return (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()


def locked_seconds(ip):
    entry = failed.get(ip)
    if not entry:
        return 0
    count, first = entry
    if time.time() - first > LOCK_SECONDS:
        failed.pop(ip, None)
        return 0
    return int(LOCK_SECONDS - (time.time() - first)) if count >= MAX_TRIES else 0


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin"):
        return redirect(url_for("index"))
    message = None
    if request.method == "POST":
        ip = client_ip()
        wait = locked_seconds(ip)
        if wait:
            message = f"Too many wrong attempts. Try again in {wait // 60 + 1} minute(s)."
        else:
            user = request.form.get("username", "")
            pwd = request.form.get("password", "")
            # compare_digest avoids timing leaks
            ok_user = hmac.compare_digest(user.encode(), ADMIN_USERNAME.encode())
            ok_pwd = hmac.compare_digest(pwd.encode(), ADMIN_PASSWORD.encode())
            if ok_user and ok_pwd:
                failed.pop(ip, None)
                session.clear()
                session["admin"] = True
                session.permanent = True
                return redirect(url_for("index"))
            count, first = failed.get(ip, [0, time.time()])
            failed[ip] = [count + 1, first]
            message = "Wrong username or password."
    return render_template("login.html", message=message), (401 if message else 200)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.before_request
def require_login():
    """Every API call needs a logged-in admin. This protects the server, not just the buttons."""
    if request.path.startswith("/api/") and not session.get("admin"):
        return jsonify({"ok": False, "error": "Please log in."}), 401


# ---------- pages ----------
@app.route("/")
def index():
    if not session.get("admin"):
        return redirect(url_for("login"))
    return render_template("index.html")


# ---------- API ----------
@app.get("/api/accounts")
def list_accounts():
    rows = get_db().execute("SELECT * FROM accounts ORDER BY created DESC, acc_no").fetchall()
    return jsonify({"ok": True, "accounts": [account_dict(r) for r in rows]})


@app.post("/api/accounts")
def create_account():
    data = request.get_json(silent=True) or {}
    acc_no = str(data.get("acc_no", "")).strip().upper()
    name = str(data.get("name", "")).strip()
    acc_type = str(data.get("type", "")).strip().upper()
    amount = parse_amount(data.get("amount"))

    if not re.fullmatch(r"[A-Z0-9]{1,20}", acc_no):
        return error("Account number must be 1-20 letters or digits.")
    if not name or len(name) > 60:
        return error("Enter the account holder name (up to 60 characters).")
    if acc_type not in MIN_BALANCE:
        return error("Account type must be Saving or Current.")
    if amount is None:
        return error("Enter a valid initial amount.")
    if amount < MIN_BALANCE[acc_type]:
        return error(
            f"Initial amount must be at least {MIN_BALANCE[acc_type]} for a "
            f"{TYPE_NAME[acc_type]} account."
        )

    db = get_db()
    if find(db, acc_no):
        return error("This account number already exists.", 409)
    db.execute(
        "INSERT INTO accounts (acc_no, name, type, balance, created) VALUES (?,?,?,?,?)",
        (acc_no, name, acc_type, amount, now()),
    )
    log_tx(db, acc_no, "OPEN", amount, amount)
    db.commit()
    return jsonify({"ok": True, "account": account_dict(find(db, acc_no))}), 201


@app.get("/api/accounts/<acc_no>")
def balance_enquiry(acc_no):
    row = find(get_db(), acc_no.upper())
    if not row:
        return error("Account not found.", 404)
    return jsonify({"ok": True, "account": account_dict(row)})


@app.post("/api/accounts/<acc_no>/deposit")
def deposit(acc_no):
    acc_no = acc_no.upper()
    amount = parse_amount((request.get_json(silent=True) or {}).get("amount"))
    if amount is None:
        return error("Enter a valid amount greater than 0.")
    db = get_db()
    row = find(db, acc_no)
    if not row:
        return error("Account not found.", 404)
    new_balance = round(row["balance"] + amount, 2)
    db.execute("UPDATE accounts SET balance = ? WHERE acc_no = ?", (new_balance, acc_no))
    log_tx(db, acc_no, "DEPOSIT", amount, new_balance)
    db.commit()
    return jsonify({"ok": True, "account": account_dict(find(db, acc_no))})


@app.post("/api/accounts/<acc_no>/withdraw")
def withdraw(acc_no):
    acc_no = acc_no.upper()
    amount = parse_amount((request.get_json(silent=True) or {}).get("amount"))
    if amount is None:
        return error("Enter a valid amount greater than 0.")
    db = get_db()
    row = find(db, acc_no)
    if not row:
        return error("Account not found.", 404)
    minimum = MIN_BALANCE[row["type"]]
    new_balance = round(row["balance"] - amount, 2)
    if new_balance < minimum:
        available = max(0, round(row["balance"] - minimum, 2))
        return error(
            f"Insufficient balance. A {TYPE_NAME[row['type']]} account must keep at least "
            f"{minimum}. You can withdraw up to {available:g}."
        )
    db.execute("UPDATE accounts SET balance = ? WHERE acc_no = ?", (new_balance, acc_no))
    log_tx(db, acc_no, "WITHDRAW", amount, new_balance)
    db.commit()
    return jsonify({"ok": True, "account": account_dict(find(db, acc_no))})


@app.put("/api/accounts/<acc_no>")
def modify_account(acc_no):
    acc_no = acc_no.upper()
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    acc_type = str(data.get("type", "")).strip().upper()
    amount = parse_amount(data.get("amount"))
    if not name or len(name) > 60:
        return error("Enter the account holder name (up to 60 characters).")
    if acc_type not in MIN_BALANCE:
        return error("Account type must be Saving or Current.")
    if amount is None:
        return error("Enter a valid amount.")
    if amount < MIN_BALANCE[acc_type]:
        return error(
            f"Balance must be at least {MIN_BALANCE[acc_type]} for a "
            f"{TYPE_NAME[acc_type]} account."
        )
    db = get_db()
    row = find(db, acc_no)
    if not row:
        return error("Account not found.", 404)
    db.execute(
        "UPDATE accounts SET name = ?, type = ?, balance = ? WHERE acc_no = ?",
        (name, acc_type, amount, acc_no),
    )
    if amount != row["balance"]:
        log_tx(db, acc_no, "EDIT", abs(amount - row["balance"]), amount)
    db.commit()
    return jsonify({"ok": True, "account": account_dict(find(db, acc_no))})


@app.delete("/api/accounts/<acc_no>")
def close_account(acc_no):
    acc_no = acc_no.upper()
    db = get_db()
    if not find(db, acc_no):
        return error("Account not found.", 404)
    db.execute("DELETE FROM accounts WHERE acc_no = ?", (acc_no,))
    db.commit()
    return jsonify({"ok": True})


@app.get("/api/transactions")
def transactions():
    acc_no = request.args.get("acc_no", "").strip().upper()
    db = get_db()
    if acc_no:
        rows = db.execute(
            "SELECT * FROM transactions WHERE acc_no = ? ORDER BY id DESC LIMIT 100", (acc_no,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT 30").fetchall()
    return jsonify({"ok": True, "transactions": [dict(r) for r in rows]})


@app.get("/api/stats")
def stats():
    db = get_db()
    row = db.execute(
        """SELECT COUNT(*) AS total,
                  COALESCE(SUM(balance), 0) AS money,
                  COALESCE(SUM(type = 'S'), 0) AS saving,
                  COALESCE(SUM(type = 'C'), 0) AS current
           FROM accounts"""
    ).fetchone()
    return jsonify({"ok": True, **dict(row)})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
