import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging
from flask import Flask
import schedule
import threading
import time
# Load environment variables from .env file
load_dotenv()

# URL of the website you want to scrape
url = os.getenv("NJUSKALO_URL")

# Headers to mimic a real browser request
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# File paths
previous_ads_file = "previous_ads.json"
current_ads_file = "current_ads.json"

# Configurable sleep interval in seconds
sleep_interval = int(os.getenv("SLEEP_INTERVAL", 900)
                     )  # Default to 15 minutes

# Logging configuration
logging.basicConfig(filename='scraper.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Exception to be raised when data fetching fails


class FetchDataError(Exception):
    pass


def fetch_data():
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

        content = response.text

        # Check if the content contains the specified message
        if "You are attempting to access Njuskalo using an anonymous private/proxy network" in content:
            print("Access denied. Please check your network settings.")
            raise FetchDataError(
                "Access denied. Please check your network settings.")

        return content

    except requests.exceptions.RequestException as e:
        print("Failed to fetch data", e)
        raise FetchDataError(f"Failed to fetch data. {e}")


def save_ads_to_file(ads, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(ads, file, ensure_ascii=False, indent=2)


def load_ads_from_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = file.read()
            return json.loads(data) if data else []
    except FileNotFoundError:
        return []
    except json.decoder.JSONDecodeError:
        return []


def extract_ads(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    ads = []
    ad_items = soup.find_all("li", class_="EntityList-item--Regular")

    for ad_item in ad_items:
        ad_details = {}

        # Extracting title, description, location, size, price, and link
        title_element = ad_item.find("h3", class_="entity-title")
        description_element = ad_item.find(
            "div", class_="entity-description-main")
        price_element = ad_item.find("strong", class_="price--hrk")
        link_element = ad_item.find("a", class_="link")

        if title_element:
            ad_details['1. title'] = title_element.text.strip()

        if description_element:
            description_text = description_element.text.strip()

            # Extracting location from the description
            location_start = description_text.find("Lokacija:")
            if location_start != -1:
                location_text = description_text[location_start +
                                                 len("Lokacija:"):].strip()
                ad_details['3. location'] = location_text

                # Remove redundant information from description
                ad_details['5. description'] = description_text.replace(
                    f"Lokacija: {location_text}", "").strip()

            # Extracting size from the description
            size_start = description_text.find("Stambena površina:")
            if size_start != -1:
                size_text = description_text[size_start +
                                             len("Stambena površina:"):].split('\n')[0].strip()
                ad_details['2. size'] = size_text

        if price_element:
            ad_details['4. price'] = price_element.text.replace(
                '\xa0', '').strip()

        if link_element:
            ad_details['6. link'] = "https://www.njuskalo.hr" + \
                link_element['href']

        ads.append(ad_details)

    # Save current ads to file
    save_ads_to_file(ads, current_ads_file)

    return ads


def check_for_new_ads(previous_ads, current_ads):
    new_ads = [ad for ad in current_ads if ad not in previous_ads]
    return new_ads


def send_notification(new_ads):
    if new_ads:
        outlook_email = os.getenv("OUTLOOK_EMAIL")
        outlook_password = os.getenv("OUTLOOK_PASSWORD")
        receiver_emails = os.getenv("RECEIVER_EMAILS").split(",")

        subject = "New Ads Found from Njuskalo"

        # Set up the HTML body
        body = "<html><body>"
        body += "<h2>New Ads Found:</h2>"

        for ad in new_ads:
            body += "<article style='margin-bottom: 20px; padding: 10px; border: 1px solid #ccc;'>"
            body += "<h3>{}</h3>".format(ad.get('1. title', ''))

            # Display other details in a table
            body += "<table>"
            for key, value in ad.items():
                body += "<tr>"
                body += "<td><strong>{}</strong></td>".format(key)
                body += "<td>{}</td>".format(value)
                body += "</tr>"
            body += "</table>"

            body += "</article>"

        body += "</body></html>"

        # Set up the MIME
        message = MIMEMultipart()
        message["From"] = outlook_email
        message["To"] = ", ".join(receiver_emails)
        message["Subject"] = subject
        message.attach(MIMEText(body, "html"))

        try:
            # Connect to Outlook SMTP server
            server = smtplib.SMTP("smtp.office365.com", 587)
            server.starttls()

            # Login to your Outlook account
            server.login(outlook_email, outlook_password)

            # Send the email
            server.sendmail(outlook_email, receiver_emails,
                            message.as_string())
            print("Notification email sent successfully!")
            logger.info("Notification email sent successfully!")

        except Exception as e:
            print("Error sending email: %s", e)
            logger.error("Error sending email: %s", e)

        finally:
            # Disconnect from the server
            server.quit()
    else:
        print("No new ads at this time. Will check again in 20 minutes")
        logger.info("No new ads at this time. Will check again in 20 minutes")


def scrape():
    try:
        logger.info("Checking for new ads at %s...", datetime.now())
        print("Checking for new ads at %s...", datetime.now())
        html_content = fetch_data()
        if html_content:
            current_ads = extract_ads(html_content)
            previous_ads = load_ads_from_file(previous_ads_file)
            new_ads = check_for_new_ads(previous_ads, current_ads)
            send_notification(new_ads)
            save_ads_to_file(current_ads, previous_ads_file)

    except FetchDataError as e:
        logger.error(str(e))

    except Exception as e:
        logger.exception("An unexpected error occurred: %s", e)

# Flask route to trigger scraping


@app.route('/scrape')
def run_scraper():
    scrape()
    return "Scraping initiated."


# Schedule scraping every 15 minutes
schedule.every(15).minutes.do(scrape)

# Function to run the scheduled tasks in a separate thread


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    # Start the Flask app in a separate thread
    flask_thread = threading.Thread(
        target=app.run, kwargs={'debug': True, 'use_reloader': False})
    flask_thread.start()

    # Start the scheduler in the main thread
    run_scheduler()
