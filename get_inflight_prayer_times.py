# get_inflight_prayer_times.py

import os
import requests
import logging
from dotenv import load_dotenv
import urllib.parse

# Load environment variables
load_dotenv()

# Get API credentials from environment variables
HALALTRIP_API_KEY = os.getenv('HALALTRIP_API_KEY')
HALALTRIP_TOKEN = os.getenv('HALALTRIP_TOKEN')

def get_inflight_prayer_times(departureAP, departureDateTime, arrivalAP, arrivalDateTime):
    try:
        logging.info(f"Fetching inflight prayer times from {departureAP} to {arrivalAP}")

        api_url = "http://api.halaltrip.com/v1/api/inflight/"
        headers = {
            'APIKEY': HALALTRIP_API_KEY,
            'TOKEN': HALALTRIP_TOKEN
        }

        # Prepare query parameters
        params = {
            'departureAP': departureAP,
            'departureDateTime': departureDateTime,
            'arrivalAP': arrivalAP,
            'arrivalDateTime': arrivalDateTime
        }

        response = requests.get(api_url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()
            # Parse and format the prayer times
            prayer_times = data.get('data', {})
            if not prayer_times:
                return "Sorry, I couldn't retrieve the inflight prayer times for your flight."

            response_text = "**🛫 Inflight Prayer Times:**\n\n"
            response_text += f"From **{departureAP}** to **{arrivalAP}**\n"
            response_text += f"Departure: {departureDateTime}\n"
            response_text += f"Arrival: {arrivalDateTime}\n\n"

            # List prayer times
            for prayer, time in prayer_times.items():
                response_text += f"**{prayer.capitalize()}**: {time}\n"

            return response_text

        else:
            logging.error(f"Error fetching inflight prayer times: {response.status_code} - {response.text}")
            return "Sorry, I couldn't retrieve the inflight prayer times at the moment."

    except Exception as e:
        logging.error(f"Exception in get_inflight_prayer_times: {e}")
        return "An error occurred while fetching inflight prayer times."
