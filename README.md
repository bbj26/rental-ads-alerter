# rental-ads-alerter

Simply scrape some advertisement websites (njuskalo.hr for start) and send email alert when new listing based on your search filters pops up. Emails go out via Brevo (SMTP).

## Installation

First run command:
`pip3 install -r requirements.txt`

Next, create `.env` file in the root project directory and copy content from `.env.template` in it. Then change the environment variables values with your own.

You need: NJUSKALO_URL (your search URL), SENDER_EMAIL, SMTP_SERVER_AUTH_EMAIL, SMTP_SERVER_AUTH_PASSWORD (Brevo SMTP key from dashboard → SMTP & API → SMTP), RECEIVER_EMAILS (comma-separated or just one). Optional: SLEEP_INTERVAL (default 900).

## Brevo

Sign up at brevo.com, go to SMTP & API → SMTP. Use that server (smtp-relay.brevo.com, port 587), login and the SMTP key as SMTP_SERVER_AUTH_EMAIL and SMTP_SERVER_AUTH_PASSWORD in .env.

## Start

`python3 scraper.py`

## Docker

Build:
`docker build -t rental-ads-alerter .`

Run:
`docker run --env-file .env rental-ads-alerter`

Run in background:
`docker run -d --env-file .env --name rental-alerter rental-ads-alerter`

Logs:
`docker logs -f rental-alerter`
