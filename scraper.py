"""
Njuskalo rental ads scraper: fetches listings, detects new ads, sends email via Brevo.
"""
import json
import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup  # pyright: ignore [reportMissingModuleSource]
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Setup: env, logging, HTTP session, paths
# -----------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    filename="scraper.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(console_handler)

url = os.getenv("NJUSKALO_URL")
logger.info("Using URL: %s", url)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,hr;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "Referer": "https://www.njuskalo.hr/",
}

session = requests.Session()
session.headers.update(BROWSER_HEADERS)

PREVIOUS_ADS_FILE = "previous_ads.json"
CURRENT_ADS_FILE = "current_ads.json"
sleep_interval = int(os.getenv("SLEEP_INTERVAL", 900))
logger.info("Configured sleep interval: %d seconds", sleep_interval)


# -----------------------------------------------------------------------------
# Fetching: get HTML from Njuskalo
# -----------------------------------------------------------------------------


class FetchDataError(Exception):
    """Raised when fetching or parsing the Njuskalo page fails."""
    pass


def fetch_data():
    logger.info("Fetching data from URL...")
    try:
        # Add a small delay to appear more human-like
        time.sleep(1)
        
        # Use session to maintain cookies and headers
        response = session.get(url, timeout=30)
        response.raise_for_status()
        logger.info("Data fetched successfully.")

        content = response.text

        if "You are attempting to access Njuskalo using an anonymous private/proxy network" in content:
            logger.error("Access denied due to proxy or network restrictions.")
            raise FetchDataError(
                "Access denied. Please check your network settings.")

        return content

    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch data: %s", e)
        raise FetchDataError(f"Failed to fetch data. {e}") from e


# -----------------------------------------------------------------------------
# Storage: read/write ads JSON
# -----------------------------------------------------------------------------


def save_ads_to_file(ads, file_path):
    logger.info("Saving ads to file: %s", file_path)
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(ads, file, ensure_ascii=False, indent=2)
    logger.info("Ads saved successfully.")


def load_ads_from_file(file_path):
    logger.info("Loading ads from file: %s", file_path)
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = file.read()
            return json.loads(data) if data else []
    except FileNotFoundError:
        logger.warning("File not found: %s. Returning empty list.", file_path)
        return []
    except json.decoder.JSONDecodeError:
        logger.error("Error decoding JSON from file: %s", file_path)
        return []


# -----------------------------------------------------------------------------
# Parsing: Njuskalo HTML -> list of ad dicts
# -----------------------------------------------------------------------------


def _parse_single_ad(ad_item):
    """Turn one <li> ad block into a dict with title, location, size, price, link."""
    ad_details = {}
    title_el = ad_item.find("h3", class_="entity-title")
    desc_el = ad_item.find("div", class_="entity-description-main")
    price_el = ad_item.find("strong", class_="price--hrk")
    link_el = ad_item.find("a", class_="link")

    if title_el:
        ad_details["1. title"] = title_el.text.strip()

    if desc_el:
        description_text = desc_el.text.strip()
        loc_start = description_text.find("Lokacija:")
        if loc_start != -1:
            location_text = description_text[loc_start + len("Lokacija:") :].strip()
            ad_details["3. location"] = location_text
            ad_details["5. description"] = description_text.replace(
                f"Lokacija: {location_text}", ""
            ).strip()
        size_start = description_text.find("Stambena površina:")
        if size_start != -1:
            size_text = (
                description_text[size_start + len("Stambena površina:") :]
                .split("\n")[0]
                .strip()
            )
            ad_details["2. size"] = size_text

    if price_el:
        ad_details["4. price"] = price_el.text.replace("\xa0", "").strip()

    if link_el:
        ad_details["6. link"] = "https://www.njuskalo.hr" + link_el["href"]

    return ad_details


def extract_ads(html_content):
    """Parse Njuskalo listing HTML into a list of ad dicts; saves to current_ads file."""
    logger.info("Extracting ads from HTML content...")
    soup = BeautifulSoup(html_content, "html.parser")
    ad_items = soup.find_all("li", class_="EntityList-item--Regular")
    ads = [_parse_single_ad(item) for item in ad_items]

    save_ads_to_file(ads, CURRENT_ADS_FILE)
    logger.info("Extracted %d ads.", len(ads))
    return ads


# -----------------------------------------------------------------------------
# Diff: which ads are new
# -----------------------------------------------------------------------------


def check_for_new_ads(previous_ads, current_ads):
    logger.info("Checking for new ads...")
    new_ads = [ad for ad in current_ads if ad not in previous_ads]
    logger.info("Found %d new ads.", len(new_ads))
    return new_ads


# -----------------------------------------------------------------------------
# Notifications: Brevo SMTP email
# -----------------------------------------------------------------------------


def _build_email_body(new_ads):
    """Build HTML body for the new-ads notification email."""
    body = "<html><body><h2>New Ads Found:</h2>"
    for ad in new_ads:
        body += "<article style='margin-bottom: 20px; padding: 10px; border: 1px solid #ccc;'>"
        body += "<h3>{}</h3><table>".format(ad.get("1. title", ""))
        for key, value in ad.items():
            body += "<tr><td><strong>{}</strong></td><td>{}</td></tr>".format(key, value)
        body += "</table></article>"
    body += "</body></html>"
    return body


def send_notification(new_ads):
    """Send an email listing new ads via Brevo SMTP; no-op if new_ads is empty."""
    if not new_ads:
        print("No new ads at this time. Will check again in 20 minutes")
        logger.info("No new ads at this time. Will check again in 20 minutes")
        return

    smtp_email = os.getenv("SMTP_SERVER_AUTH_EMAIL")
    smtp_password = os.getenv("SMTP_SERVER_AUTH_PASSWORD")
    receiver_emails = os.getenv("RECEIVER_EMAILS", "").split(",")
    sender_email = os.getenv("SENDER_EMAIL")

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = ", ".join(receiver_emails)
    message["Subject"] = "New Ads Found from Njuskalo"
    message.attach(MIMEText(_build_email_body(new_ads), "html"))

    server = None
    try:
        server = smtplib.SMTP("smtp-relay.brevo.com", 587)
        server.starttls()
        server.login(smtp_email, smtp_password)
        server.sendmail(smtp_email, receiver_emails, message.as_string())
        print("Notification email sent successfully!")
        logger.info("Notification email sent successfully!")
    except Exception as e:
        print("Error sending email: %s", e)
        logger.error("Error sending email: %s", e)
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass


# -----------------------------------------------------------------------------
# Main flow: fetch -> parse -> diff -> notify -> persist
# -----------------------------------------------------------------------------


def scrape():
    """Run one full cycle: fetch page, parse ads, diff with previous, email new ones, save state."""
    logger.info("Starting scrape process...")
    try:
        html_content = fetch_data()
        if html_content:
            current_ads = extract_ads(html_content)
            previous_ads = load_ads_from_file(PREVIOUS_ADS_FILE)
            new_ads = check_for_new_ads(previous_ads, current_ads)
            send_notification(new_ads)
            save_ads_to_file(current_ads, PREVIOUS_ADS_FILE)
    except FetchDataError as e:
        logger.error(str(e))
    except Exception as e:
        logger.exception("An unexpected error occurred: %s", e)


if __name__ == "__main__":
    logger.info("Running initial scrape...")
    scrape()
