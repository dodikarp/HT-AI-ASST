# get_prayer_times.py

import os
import requests
import logging
from dotenv import load_dotenv
from helpers import get_lat_long, get_timezone

# Load environment variables
load_dotenv()

# Get API credentials from environment variables
HALALTRIP_API_KEY = os.getenv('HALALTRIP_API_KEY')
HALALTRIP_TOKEN = os.getenv('HALALTRIP_TOKEN')

def get_prayer_times(city, country, specific_prayer=None):
    try:
        lat, lng = get_lat_long(city, country)
        if not lat or not lng:
            return "Could not find the location."

        timezone = get_timezone(lat, lng)
        if not timezone:
            return "Could not retrieve the timezone."

        logging.info(f"Fetching prayer times for city: {city}, country: {country} in timezone {timezone}")

        api_url = f"http://api.halaltrip.com/v1/api/prayertimes/"
        params = {
            'lat': lat,
            'lng': lng,
            'timeZoneId': timezone
        }
        headers = {
            'APIKEY': HALALTRIP_API_KEY,
            'TOKEN': HALALTRIP_TOKEN
        }
        response = requests.get(api_url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()
            logging.info(f"Response from Halaltrip API: {data}")

            # Parse the data to get timings
            prayer_data = data.get('prayer', {})
            if not prayer_data:
                return "Could not retrieve prayer times."

            # Get the date key (e.g., '15-10-2024')
            date_key = next(iter(prayer_data))
            timings = prayer_data.get(date_key, {})
            if not timings:
                return "Could not retrieve prayer times."

            if specific_prayer:
                specific_time = timings.get(specific_prayer.capitalize())
                logging.info(f"Specific prayer time ({specific_prayer}): {specific_time}")
                return specific_time or f"{specific_prayer.capitalize()} time not available."
            else:
                formatted_timings = (
                    f"**🕌 Here are the prayer times for {city}, {country} on {date_key}:**\n\n"
                    f"**Fajr** ⏰: {timings.get('Fajr', 'N/A')}\n"
                    f"**Dhuhr** ⏰: {timings.get('Dhuhr', 'N/A')}\n"
                    f"**Asr** ⏰: {timings.get('Asr', 'N/A')}\n"
                    f"**Maghrib** ⏰: {timings.get('Maghrib', 'N/A')}\n"
                    f"**Isha** ⏰: {timings.get('Isha', 'N/A')}\n"
                )
                return formatted_timings
        else:
            logging.error(f"Error fetching prayer times: {response.status_code} - {response.text}")
            return "Sorry, I couldn't fetch the prayer times at the moment."
    except Exception as e:
        logging.error(f"Error fetching prayer times: {e}")
        return f"Error fetching prayer times: {e}"
