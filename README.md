# Ledgerly - Bank Management System (Flask + SQLite)

Web version of the console Bank Management System. Same features: new account,
deposit, withdraw, balance enquiry, all account holders, edit account, close account.
Extra: dashboard totals, search, recent activity (transaction history).

Rules (same as the console project)
- Saving account: initial amount and minimum balance 500
- Current account: initial amount and minimum balance 1000
- Account number can be letters or digits (no more int() crash)

## Run on your PC
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000

## Deploy on Render (free)
1. Push this folder to a GitHub repo.
2. Render -> New -> Web Service -> pick the repo.
3. Build command: pip install -r requirements.txt
4. Start command: gunicorn app:app
5. Deploy.

Note: on Render free plan the disk is temporary, so data resets when the service
restarts. For permanent data, move to a Render PostgreSQL database later.
