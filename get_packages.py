# get_packages.py

import requests
import logging
from dotenv import load_dotenv
import os
import re

# Load environment variables
load_dotenv()

# Get API credentials from environment variables
HALALTRIP_API_KEY = os.getenv('HALALTRIP_API_KEY')
HALALTRIP_TOKEN = os.getenv('HALALTRIP_TOKEN')

def get_all_packages():
    api_url = "http://api.halaltrip.com/v1/api/packages"
    headers = {
        'APIKEY': HALALTRIP_API_KEY,
        'TOKEN': HALALTRIP_TOKEN
    }
    try:
        all_packages = []
        page = 1

        while True:
            params = {'page': page}
            response = requests.get(api_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            packages = data.get('data', [])

            if not packages:
                logging.info(f"No more packages found at page {page}. Ending pagination.")
                break  # No more packages to fetch

            logging.info(f"Fetched {len(packages)} packages from page {page}.")
            all_packages.extend(packages)
            page += 1  # Move to the next page

        return all_packages

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching packages: {e}")
        return None

def get_package_by_id(package_id):
    url = f"http://api.halaltrip.com/v1/api/package/{package_id}"
    headers = {
        'APIKEY': HALALTRIP_API_KEY,
        'TOKEN': HALALTRIP_TOKEN
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        package = response.json().get('data', {})
        return package
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching package with ID {package_id}: {e}")
        return None

def search_packages_by_keyword(keyword, duration=None, special_request=None):
    packages = get_all_packages()
    if not packages:
        return None
    matching_packages = []
    keyword_lower = keyword.lower() if keyword else ''
    for package in packages:
        name = package.get('name', '').lower()
        description = package.get('description', '').lower()
        package_duration = package.get('duration', '')
        # Clean the description to remove HTML tags
        description = re.sub('<[^<]+?>', '', description)
        if ((keyword_lower in name or keyword_lower in description) or (special_request and special_request in description)):
            if duration is None or package_duration == str(duration):
                matching_packages.append(package)
    return matching_packages
