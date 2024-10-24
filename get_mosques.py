# get_mosques.py

import os
import requests
import logging
from dotenv import load_dotenv
import time
from math import radians, cos, sin, asin, sqrt
import urllib.parse

# Load environment variables
load_dotenv()

# Get API credentials from environment variables
HALALTRIP_API_KEY = os.getenv('HALALTRIP_API_KEY')
HALALTRIP_TOKEN = os.getenv('HALALTRIP_TOKEN')

# Global variables for caching
_cached_mosques_data = None
_mosques_last_fetched = 0  # Timestamp of last fetch

def haversine(lon1, lat1, lon2, lat2):
    # Haversine formula
    lon1, lat1, lon2, lat2 = map(
        radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * \
        cos(lat2) * sin(dlon / 2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of Earth in kilometers
    return c * r

def get_mosques(area=None, num_results=10, latitude=None, longitude=None, radius=5):
    global _cached_mosques_data, _mosques_last_fetched

    # Check if data is cached and if it's recent (e.g., within the last day)
    current_time = time.time()
    if _cached_mosques_data is not None and (current_time - _mosques_last_fetched) < 86400:
        all_mosques = _cached_mosques_data
        logging.info("Using cached mosque data.")
    else:
        # Fetch data from API
        try:
            logging.info("Fetching mosque data from API.")
            api_url = f"http://api.halaltrip.com/v1/api/mosques"
            headers = {
                'APIKEY': HALALTRIP_API_KEY,
                'TOKEN': HALALTRIP_TOKEN
            }

            all_mosques = []
            page = 1  # Start from the first page

            while True:
                params = {'page': page}
                response = requests.get(api_url, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    mosques = data.get('data', [])

                    if not mosques:
                        logging.info(f"No more mosques found at page {page}. Ending pagination.")
                        break  # Stop if no more mosques

                    logging.info(f"Fetched {len(mosques)} mosques from page {page}.")
                    all_mosques.extend(mosques)
                    page += 1  # Move to the next page

                else:
                    logging.error(f"Error fetching mosques on page {page}: {response.status_code} - {response.text}")
                    return "Sorry, I couldn't fetch the list of mosques at the moment."

            # Cache the data
            _cached_mosques_data = all_mosques
            _mosques_last_fetched = current_time

        except Exception as e:
            logging.error(f"Error fetching mosques: {e}")
            return f"Error fetching mosques: {e}"

    try:
        matches = []

        if latitude and longitude:
            # Find mosques within the specified radius
            for mosque in all_mosques:
                mosque_lat = float(mosque.get('latitude', 0))
                mosque_lon = float(mosque.get('longitude', 0))
                distance = haversine(longitude, latitude, mosque_lon, mosque_lat)
                if distance <= radius:
                    mosque['distance'] = distance
                    matches.append(mosque)

            # Sort the matches by distance
            matches.sort(key=lambda x: x['distance'])

            if not matches:
                return f"No mosques found within {radius} km of your location."

            # Format the response
            response_text = f"**🕌 Here are some mosques within {radius} km of your location:**\n\n"

            for i, mosque in enumerate(matches[:num_results]):
                name = mosque.get('name', 'N/A').strip()
                address = mosque.get('address', 'N/A').strip()
                distance = mosque.get('distance', 0)

                # Generate Google Maps link using coordinates
                mosque_lat = float(mosque.get('latitude', 0))
                mosque_lon = float(mosque.get('longitude', 0))
                maps_url = f"https://www.google.com/maps/search/?api=1&query={mosque_lat},{mosque_lon}"

                response_text += (
                    f"{i+1}. **{name}**\n"
                    f"   📍 Address: {address}\n"
                    f"   📏 Distance: {distance:.2f} km "
                    f"[[(map)]({maps_url})]\n\n"
                )

            total_found = len(matches)
            if total_found < num_results:
                response_text += f"Note: There are only {total_found} mosques within {radius} km of your location.\n"

            return response_text

        elif area:
            # Existing area-based search logic
            area_lower = area.lower()
            area_keywords = area_lower.split()

            for mosque in all_mosques:
                address = mosque.get('address', '').lower()
                name = mosque.get('name', '').lower()
                combined_text = f"{name} {address}"

                if all(keyword in combined_text for keyword in area_keywords):
                    matches.append(mosque)

            # Remove duplicates
            matches = list({mosque['id']: mosque for mosque in matches}.values())

            if not matches:
                return f"No mosques found in {area.title()}."

            # Format the response
            response_text = f"**🕌 Here are some mosques in {area.title()}:**\n\n"

            for i, mosque in enumerate(matches[:num_results]):
                name = mosque.get('name', 'N/A').strip()
                address = mosque.get('address', 'N/A').strip()

                # Generate Google Maps link using address
                encoded_address = urllib.parse.quote_plus(address)
                maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_address}"

                response_text += (
                    f"{i+1}. **{name}**\n"
                    f"   📍 Address: {address}\n"
                    f"   [[(map)]({maps_url})]\n\n"
                )

            total_found = len(matches)
            if total_found < num_results:
                response_text += f"Note: There are only {total_found} mosques in {area.title()}.\n"

            return response_text

        else:
            return "Please provide an area or enable location services for nearby searches."

    except Exception as e:
        logging.error(f"Error processing mosques: {e}")
        return f"Error processing mosques: {e}"
