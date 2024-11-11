# get_restaurants.py

import os
import requests
import logging
from dotenv import load_dotenv
import time
from math import radians, cos, sin, asin, sqrt
import urllib.parse
import re
import difflib

# Load environment variables
load_dotenv()

# Get API credentials from environment variables
HALALTRIP_API_KEY = os.getenv('HALALTRIP_API_KEY')
HALALTRIP_TOKEN = os.getenv('HALALTRIP_TOKEN')

# Global variables for caching
_cached_restaurants_data = None
_restaurants_last_fetched = 0  # Timestamp of last fetch

def haversine(lon1, lat1, lon2, lat2):
    # Haversine formula to calculate distance between two points on Earth
    lon1, lat1, lon2, lat2 = map(
        radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * \
        cos(lat2) * sin(dlon / 2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of Earth in kilometers
    return c * r

def fetch_all_restaurants():
    global _cached_restaurants_data, _restaurants_last_fetched

    current_time = time.time()
    if _cached_restaurants_data is not None and (current_time - _restaurants_last_fetched) < 86400:
        logging.info("Using cached restaurant data.")
        return _cached_restaurants_data

    try:
        logging.info("Fetching restaurant data from API.")
        api_url = f"http://api.halaltrip.com/v1/api/restaurants"
        headers = {
            'APIKEY': HALALTRIP_API_KEY,
            'TOKEN': HALALTRIP_TOKEN
        }

        all_restaurants = []
        page = 1  # Start from the first page

        while True:
            params = {'page': page}
            response = requests.get(api_url, params=params, headers=headers)

            if response.status_code == 200:
                data = response.json()
                restaurants = data.get('data', [])

                if not restaurants:
                    logging.info(f"No more restaurants found at page {page}. Ending pagination.")
                    break  # Stop if no more restaurants

                logging.info(f"Fetched {len(restaurants)} restaurants from page {page}.")
                all_restaurants.extend(restaurants)
                page += 1  # Move to the next page

            else:
                logging.error(f"Error fetching restaurants on page {page}: {response.status_code} - {response.text}")
                return None

        # Cache the data
        _cached_restaurants_data = all_restaurants
        _restaurants_last_fetched = current_time
        return all_restaurants

    except Exception as e:
        logging.error(f"Error fetching restaurants: {e}")
        return None

def get_restaurant_by_name(restaurant_name):
    try:
        all_restaurants = fetch_all_restaurants()
        if all_restaurants is None:
            return "Sorry, I couldn't fetch the restaurant data at the moment."

        # First, check for exact matches
        exact_matches = [restaurant for restaurant in all_restaurants if restaurant.get('restaurantname', '').strip().lower() == restaurant_name.lower()]
        if exact_matches:
            restaurant_id = exact_matches[0].get('id')
            return get_restaurant_details(restaurant_id)

        # If no exact matches, use fuzzy matching
        restaurant_names = [restaurant.get('restaurantname', '').strip() for restaurant in all_restaurants]
        close_matches = difflib.get_close_matches(restaurant_name.lower(), [name.lower() for name in restaurant_names], n=5, cutoff=0.8)

        if not close_matches:
            return None

        # Find the matching restaurants
        matches = []
        for restaurant in all_restaurants:
            name = restaurant.get('restaurantname', '').strip()
            if name.lower() in close_matches:
                matches.append(restaurant)

        if len(matches) == 1:
            restaurant_id = matches[0].get('id')
            return get_restaurant_details(restaurant_id)
        else:
            # List the matches
            response_text = "I found multiple restaurants matching your query:\n\n"
            for restaurant in matches:
                response_text += f"- **{restaurant.get('restaurantname', 'N/A')}**\n"
            response_text += "\nPlease specify the exact restaurant name."
            return response_text

    except Exception as e:
        logging.error(f"Error getting restaurant by name: {e}")
        return f"Error getting restaurant by name: {e}"

def get_restaurant_by_exact_name(restaurant_name):
    try:
        all_restaurants = fetch_all_restaurants()
        if all_restaurants is None:
            return None

        for restaurant in all_restaurants:
            name = restaurant.get('restaurantname', '').strip()
            if name == restaurant_name:
                restaurant_id = restaurant.get('id')
                return get_restaurant_details(restaurant_id)

        return None

    except Exception as e:
        logging.error(f"Error getting restaurant by exact name: {e}")
        return None

def get_restaurant_details(restaurant_id):
    try:
        api_url = f"http://api.halaltrip.com/v1/api/restaurant/{restaurant_id}"
        headers = {
            'APIKEY': HALALTRIP_API_KEY,
            'TOKEN': HALALTRIP_TOKEN
        }
        response = requests.get(api_url, headers=headers)

        if response.status_code == 200:
            restaurant = response.json().get('data', {})
            if not restaurant:
                return "Sorry, I couldn't find details for that restaurant."

            name = restaurant.get('restaurantname', 'N/A').strip()
            address = restaurant.get('address', 'N/A').strip()
            description = restaurant.get('description', 'No description available.').strip()

            # Generate Google Maps link using coordinates if available
            restaurant_lat = float(restaurant.get('latitude', 0))
            restaurant_lon = float(restaurant.get('longitude', 0))
            if restaurant_lat != 0 and restaurant_lon != 0:
                maps_url = f"https://www.google.com/maps/search/?api=1&query={restaurant_lat},{restaurant_lon}"
            else:
                # Use address if coordinates are not available
                encoded_address = urllib.parse.quote_plus(address)
                maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_address}"

            response_text = f"""
**{name}**

📍 Address: {address}

📝 Description: {description}

🌐 [(View on Map)]({maps_url})

*Let me know if you need more information about this restaurant.*
"""
            return response_text.strip()

        else:
            logging.error(f"Error fetching restaurant details: {response.status_code} - {response.text}")
            return "Sorry, I couldn't retrieve the restaurant details at the moment."

    except Exception as e:
        logging.error(f"Error fetching restaurant details: {e}")
        return f"Error fetching restaurant details: {e}"

def get_restaurants(area=None, city=None, country=None, cuisine=None):
    try:
        logging.info(f"Fetching restaurants for area: {area}, city: {city}, country: {country}, cuisine: {cuisine}")

        all_restaurants = fetch_all_restaurants()
        if all_restaurants is None:
            return "Sorry, I couldn't fetch the restaurant data at the moment."

        # Filter the restaurants based on area, city, country, and cuisine
        matches = []

        area_keywords = []
        if area:
            area_lower = area.lower()
            area_keywords = area_lower.split()

        for restaurant in all_restaurants:
            address = restaurant.get('address', '').lower()
            name = restaurant.get('restaurantname', '').lower()

            # Combine address and name for matching
            combined_text = f"{name} {address}"

            # Check for area match
            area_match = True
            if area_keywords:
                area_match = all(keyword in combined_text for keyword in area_keywords)

            # Filter by cuisine if provided (Note: Cuisine field may not exist)
            cuisine_match = True
            if cuisine:
                # Assuming 'description' field might contain cuisine information
                description = restaurant.get('description', '').strip().lower()
                if cuisine.lower() not in description:
                    cuisine_match = False

            if area_match and cuisine_match:
                matches.append(restaurant)

        # Handle case when no restaurants are found
        if not matches:
            location_str = ''
            if area:
                location_str = area.title()
            elif city and country:
                location_str = f"{city.title()}, {country.title()}"
            elif city:
                location_str = city.title()
            elif country:
                location_str = country.title()
            else:
                location_str = 'the specified area'
            return f"No halal {cuisine or ''} restaurants found in {location_str}."

        # Format the response with the top 5 restaurants
        location_str = ''
        if area:
            location_str = area.title()
        elif city and country:
            location_str = f"{city.title()}, {country.title()}"
        elif city:
            location_str = city.title()
        elif country:
            location_str = country.title()
        else:
            location_str = 'the specified area'

        response_text = f"**🍽️ Here are some halal restaurants in {location_str}"
        if cuisine:
            response_text += f" serving {cuisine} cuisine"
        response_text += ":**\n\n"

        for i, restaurant in enumerate(matches[:5]):  # Show top 5 restaurants
            name = restaurant.get('restaurantname', 'N/A').strip()
            address = restaurant.get('address', 'N/A').strip()
            description = restaurant.get('description', '').strip()

            # Generate Google Maps link using coordinates if available
            restaurant_lat = float(restaurant.get('latitude', 0))
            restaurant_lon = float(restaurant.get('longitude', 0))
            if restaurant_lat != 0 and restaurant_lon != 0:
                maps_url = f"https://www.google.com/maps/search/?api=1&query={restaurant_lat},{restaurant_lon}"
            else:
                # Use address if coordinates are not available
                encoded_address = urllib.parse.quote_plus(address)
                maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_address}"

            response_text += (
                f"{i+1}. **{name}**\n"
                f"   📍 Address: {address}\n"
                f"   📝 Description: {description or 'No description available'}\n"
                f"   🌐 [(View on Map)]({maps_url})\n\n"
            )

        return response_text

    except Exception as e:
        logging.error(f"Error fetching restaurants: {e}")
        return f"Error fetching restaurants: {e}"

def get_restaurants_nearby(latitude, longitude, radius=5, cuisine=None, dietary_preferences=None):
    try:
        all_restaurants = fetch_all_restaurants()
        if all_restaurants is None:
            return "Sorry, I couldn't fetch the restaurant data at the moment."

        # Filter the restaurants within the specified radius
        matches = []

        for restaurant in all_restaurants:
            restaurant_lat = float(restaurant.get('latitude', 0))
            restaurant_lon = float(restaurant.get('longitude', 0))
            if restaurant_lat == 0 and restaurant_lon == 0:
                continue  # Skip if coordinates are not available
            distance = haversine(longitude, latitude, restaurant_lon, restaurant_lat)
            if distance <= radius:
                # Filter by cuisine if provided
                if cuisine:
                    # Assuming 'description' field might contain cuisine information
                    description = restaurant.get('description', '').strip().lower()
                    if cuisine.lower() not in description:
                        continue  # Skip if cuisine doesn't match
                # Filter by dietary preferences if needed (not in data)
                restaurant['distance'] = distance
                matches.append(restaurant)

        # Sort the matches by distance
        matches.sort(key=lambda x: x['distance'])

        if not matches:
            return f"No halal restaurants found within {radius} km of your location."

        # Format the response
        response_text = f"**🍽️ Here are some halal restaurants within {radius} km of your location"
        if cuisine:
            response_text += f" serving {cuisine} cuisine"
        response_text += ":**\n\n"

        for i, restaurant in enumerate(matches[:5]):  # Show top 5 restaurants
            name = restaurant.get('restaurantname', 'N/A').strip()
            address = restaurant.get('address', 'N/A').strip()
            description = restaurant.get('description', '').strip()
            distance = restaurant.get('distance', 0)

            # Generate Google Maps link using coordinates
            restaurant_lat = float(restaurant.get('latitude', 0))
            restaurant_lon = float(restaurant.get('longitude', 0))
            maps_url = f"https://www.google.com/maps/search/?api=1&query={restaurant_lat},{restaurant_lon}"

            response_text += (
                f"{i+1}. **{name}**\n"
                f"   📍 Address: {address}\n"
                f"   📏 Distance: {distance:.2f} km\n"
                f"   📝 Description: {description or 'No description available'}\n"
                f"   🌐 [(View on Map)]({maps_url})\n\n"
            )

        total_found = len(matches)
        if total_found < 5:
            response_text += f"Note: There are only {total_found} halal restaurants within {radius} km of your location.\n"

        return response_text

    except Exception as e:
        logging.error(f"Error processing restaurants: {e}")
        return f"Error processing restaurants: {e}"
