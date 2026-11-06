# Ledgerly - Bank Management System (Flask + SQLite)

Web version of the console Bank Management System. Same features: new account,
deposit, withdraw, balance enquiry, all account holders, edit account, close account.
Extra: dashboard totals, search, recent activity (transaction history).

Security
- One admin login only. There is no register page.
- Every API call needs a logged-in session (checked on the server, not just in the page).
- 5 wrong passwords from one IP -> locked for 5 minutes.
- Admin username and password come from environment variables, never from the code.

Rules (same as the console project)
- Saving account: initial amount and minimum balance 500
- Current account: initial amount and minimum balance 1000
- Account number can be letters or digits (no more int() crash)

## Run on your PC
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000 and sign in with  admin / admin123  (local testing only).
To use your own login locally (PowerShell):
    $env:ADMIN_USERNAME="myname"; $env:ADMIN_PASSWORD="MyStrongPass"; python app.py

## Deploy on Render (free)
1. Push this folder to a GitHub repo.
2. Render -> New -> Web Service -> pick the repo.
3. Build command: pip install -r requirements.txt
4. Start command: gunicorn app:app
5. Open the Environment tab and add:
       ADMIN_USERNAME = your admin name
       ADMIN_PASSWORD = a strong password (required: the app will not start without it)
       SECRET_KEY     = any long random text (keeps you logged in after restarts)
6. Deploy.

Note: on Render free plan the disk is temporary, so data resets when the service
restarts. For permanent data, move to a Render PostgreSQL database later.
