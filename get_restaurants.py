# get_restaurants.py

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

def get_restaurants(area=None, city=None, country=None, cuisine=None):
    try:
        logging.info(f"Fetching restaurants for area: {area}, city: {city}, country: {country}, cuisine: {cuisine}")

        global _cached_restaurants_data, _restaurants_last_fetched

        # Check if data is cached and if it's recent (e.g., within the last day)
        current_time = time.time()
        if _cached_restaurants_data is not None and (current_time - _restaurants_last_fetched) < 86400:
            all_restaurants = _cached_restaurants_data
            logging.info("Using cached restaurant data.")
        else:
            # Fetch data from API
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
                        return "Sorry, I couldn't fetch the list of restaurants at the moment."

                # Cache the data
                _cached_restaurants_data = all_restaurants
                _restaurants_last_fetched = current_time

            except Exception as e:
                logging.error(f"Error fetching restaurants: {e}")
                return f"Error fetching restaurants: {e}"

        # Filter the restaurants based on area, city, and country
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

            # Check for city and country match
            city_info = restaurant.get('city')
            country_info = restaurant.get('country')

            city_match = True
            country_match = True

            if city:
                if isinstance(city_info, dict):
                    city_name = city_info.get('name', '').strip().lower()
                    city_match = city.lower() == city_name
                else:
                    city_match = False

            if country:
                if isinstance(country_info, dict):
                    country_name = country_info.get('name', '').strip().lower()
                    country_match = country.lower() == country_name
                else:
                    country_match = False

            # Filter by cuisine if provided
            cuisine_match = True
            if cuisine:
                restaurant_cuisine = restaurant.get('cuisine', '').strip().lower()
                cuisine_match = cuisine.lower() in restaurant_cuisine

            if area_match and city_match and country_match and cuisine_match:
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
            restaurant_cuisine = restaurant.get('cuisine', 'N/A').strip()
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
                f"   🍴 Cuisine: {restaurant_cuisine}\n"
                f"   📝 Description: {description}\n"
                f"   🌐 [(View on Map)]({maps_url})\n\n"
            )

        return response_text

    except Exception as e:
        logging.error(f"Error fetching restaurants: {e}")
        return f"Error fetching restaurants: {e}"

def get_restaurants_nearby(latitude, longitude, radius=5, cuisine=None, dietary_preferences=None):
    try:
        global _cached_restaurants_data, _restaurants_last_fetched

        # Check if data is cached and if it's recent (e.g., within the last day)
        current_time = time.time()
        if _cached_restaurants_data is not None and (current_time - _restaurants_last_fetched) < 86400:
            all_restaurants = _cached_restaurants_data
            logging.info("Using cached restaurant data.")
        else:
            # Fetch data from API
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
                        return "Sorry, I couldn't fetch the list of restaurants at the moment."

                # Cache the data
                _cached_restaurants_data = all_restaurants
                _restaurants_last_fetched = current_time

            except Exception as e:
                logging.error(f"Error fetching restaurants: {e}")
                return f"Error fetching restaurants: {e}"

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
                    restaurant_cuisine = restaurant.get('cuisine', '').strip().lower()
                    if cuisine.lower() not in restaurant_cuisine:
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
            restaurant_cuisine = restaurant.get('cuisine', 'N/A').strip()
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
                f"   🍴 Cuisine: {restaurant_cuisine}\n"
                f"   📝 Description: {description}\n"
                f"   🌐 [(View on Map)]({maps_url})\n\n"
            )

        total_found = len(matches)
        if total_found < 5:
            response_text += f"Note: There are only {total_found} halal restaurants within {radius} km of your location.\n"

        return response_text

    except Exception as e:
        logging.error(f"Error processing restaurants: {e}")
        return f"Error processing restaurants: {e}"
