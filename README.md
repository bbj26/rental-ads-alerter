# rental-ads-alerter

Simply scrape some advertisement websites (njuskalo.hr for start) and send email alert when new listing based on your search filters pops up

## Installation

First run command:
`pip3 install -r requirements.txt`

Next, create `.env` file in the root project directory and copy content from `.env.template` in it. Then change the environment variables values with your own.

## Start

`python3 scraper.py`

Go to http://127.0.0.1:5000/scrape to start scraping process
