# helpers.py

import os
import requests
import logging
import spacy
from spacy.matcher import Matcher
from dotenv import load_dotenv
import docx  # Library to handle .docx files
import re

# Load environment variables
load_dotenv()

# Get Google API key from environment variables
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# Load the NLP model for English
nlp = spacy.load("en_core_web_sm")

def extract_location(message):
    # Normalize the message by capitalizing it
    message = message.title()
    doc = nlp(message)
    locations = []
    non_location_words = [word.lower() for word in [
        'mosque', 'mosques', 'masjid', 'masjids',
        'restaurant', 'restaurants', 'food', 'eat',
        'prayer', 'prayers', 'time', 'times',
        'qibla', 'direction', 'halal', 'near', 'in', 'at', 'the', 'list', 'show', 'find', 'display',
        # Add prayer names to the non-location words
        'fajr', 'dhuhr', 'asr', 'maghrib', 'isha',
        # Add common misspellings or variations
        'mahgrib', 'magrib', 'asar', 'dhuhr', 'zuhr', 'fajar', 'eisha', 'isha',
        # Add package-related words
        'package', 'packages', 'travel', 'tour', 'trip', 'vacation'
    ]]

    # Define the matcher
    matcher = Matcher(nlp.vocab)
    pattern = [{'POS': 'PROPN'}]
    matcher.add("ProperNoun", [pattern])
    matches = matcher(doc)

    # Extract matched proper nouns
    for match_id, start, end in matches:
        span = doc[start:end]
        if span.text.lower() not in non_location_words and not span.text.isdigit():
            locations.append(span.text)

    # Include entities recognized by NER
    for ent in doc.ents:
        if ent.label_ in ["GPE", "LOC", "FAC", "ORG"]:
            if ent.text.lower() not in non_location_words and ent.text not in locations and not ent.text.isdigit():
                locations.append(ent.text)

    return locations

def detect_city_country(locations):
    for loc in locations:
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={loc}&key={GOOGLE_API_KEY}"
        response = requests.get(geocode_url)
        if response.status_code == 200:
            data = response.json()
            if len(data['results']) > 0:
                address_components = data['results'][0]['address_components']
                city, country = None, None

                for component in address_components:
                    if "locality" in component["types"]:
                        city = component["long_name"]
                    if "country" in component["types"]:
                        country = component["long_name"]

                if not city and country and country.lower() == loc.lower():
                    city = country

                if city and country:
                    return city, country
        else:
            logging.error(f"Error fetching geocode data for {loc}")
    return None, None

def get_lat_long(city, country):
    geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={city},{country}&key={GOOGLE_API_KEY}"
    response = requests.get(geocode_url)
    if response.status_code == 200:
        data = response.json()
        if len(data['results']) > 0:
            lat = data['results'][0]['geometry']['location']['lat']
            lng = data['results'][0]['geometry']['location']['lng']
            logging.info(f"Latitude: {lat}, Longitude: {lng}")
            return lat, lng
    logging.error(f"Error fetching lat/lng for {city}, {country}")
    return None, None

def get_timezone(lat, lng):
    import time
    timestamp = int(time.time())
    timezone_url = f"https://maps.googleapis.com/maps/api/timezone/json?location={lat},{lng}&timestamp={timestamp}&key={GOOGLE_API_KEY}"
    response = requests.get(timezone_url)
    if response.status_code == 200:
        data = response.json()
        logging.info(f"Timezone ID: {data['timeZoneId']}")
        return data['timeZoneId']
    logging.error(f"Error fetching timezone for {lat}, {lng}")
    return None

def read_word_doc(filepath):
    doc = docx.Document(filepath)
    full_text = []
    for paragraph in doc.paragraphs:
        full_text.append(paragraph.text)
    return "\n".join(full_text)

def extract_flight_details(message):
    try:
        # Initialize variables
        departureAP = None
        arrivalAP = None
        departureDateTime = None
        arrivalDateTime = None

        # Extract IATA codes
        iata_codes = re.findall(r'\b([A-Z]{3})\b', message)
        if len(iata_codes) >= 2:
            departureAP = iata_codes[0].upper()
            arrivalAP = iata_codes[1].upper()
        else:
            logging.info("Could not find sufficient IATA codes in the message.")
            return None

        # Extract departure date and time
        departure_match = re.search(r'departing\s+(?:on\s+)?([\d-]+\s+(?:at\s+)?[\d:]+)', message, re.IGNORECASE)
        if departure_match:
            departureDateTime = departure_match.group(1)
        else:
            logging.info("Could not find departure date and time in the message.")
            return None

        # Extract arrival date and time
        arrival_match = re.search(r'arriving\s+(?:on\s+)?([\d-]+\s+(?:at\s+)?[\d:]+)', message, re.IGNORECASE)
        if arrival_match:
            arrivalDateTime = arrival_match.group(1)
        else:
            # If arrival date is not specified, assume same as departure date
            arrival_time_match = re.search(r'arriving\s+(?:at\s+)?([\d:]+)', message, re.IGNORECASE)
            if arrival_time_match:
                arrivalTime = arrival_time_match.group(1)
                # Extract departure date to use for arrival date
                departure_date_match = re.search(r'([\d-]+)\s+(?:at\s+)?[\d:]+', departureDateTime)
                if departure_date_match:
                    arrivalDateTime = f"{departure_date_match.group(1)} at {arrivalTime}"
                else:
                    logging.info("Could not extract departure date for arrival date.")
                    return None
            else:
                logging.info("Could not find arrival date and time in the message.")
                return None

        # Clean up date and time formats if necessary
        departureDateTime = departureDateTime.replace('on ', '').strip()
        arrivalDateTime = arrivalDateTime.replace('on ', '').strip()

        return {
            'departureAP': departureAP,
            'departureDateTime': departureDateTime,
            'arrivalAP': arrivalAP,
            'arrivalDateTime': arrivalDateTime
        }

    except Exception as e:
        logging.error(f"Error extracting flight details: {e}")
        return None

def extract_restaurant_name(message):
    # This function attempts to extract the restaurant name from the user's message
    message_lower = message.lower()
    trigger_phrases = ['tell me more about', 'more info on', 'information about', 'details on']
    for phrase in trigger_phrases:
        if phrase in message_lower:
            name_part = message_lower.split(phrase)[1]
            # Remove any leading 'in', 'at', 'located in', etc.
            name_part = re.sub(r'\b(in|at|located in|in the city of)\b', '', name_part, flags=re.IGNORECASE).strip()
            # Remove any location information at the end
            name_part = re.sub(r'\bin.*', '', name_part, flags=re.IGNORECASE).strip()
            # Capitalize each word
            restaurant_name = ' '.join(word.capitalize() for word in name_part.split())
            return restaurant_name.strip()
    # If no trigger phrase is found, return the message as the restaurant name
    return message.strip().title()

def extract_duration(message):
    # Extract duration in days or nights from the message
    match = re.search(r'(\d+)\s*(?:day|days|night|nights)', message, re.IGNORECASE)
    if match:
        return int(match.group(1))
    else:
        return None

def extract_special_request(message):
    # Extract special requests like 'honeymoon', 'family', 'adventure', etc.
    special_requests_keywords = ['honeymoon', 'family', 'adventure', 'luxury', 'budget', 'romantic', 'solo', 'group']
    for keyword in special_requests_keywords:
        if keyword.lower() in message.lower():
            return keyword.lower()
    return None

def extract_keyword(message):
    # Remove duration phrases from the message
    message = re.sub(r'\d+\s*(?:day|days|night|nights)', '', message, flags=re.IGNORECASE)
    # Implement logic to extract keywords from the user's message
    match = re.search(r'packages (?:to|for|in|about|on)\s+(.*)', message, re.IGNORECASE)
    if match:
        keyword = match.group(1)
        return keyword.strip()
    else:
        # If no explicit keyword, attempt to extract location
        locations = extract_location(message)
        if locations:
            return ' '.join(locations)
        else:
            # If still no keyword, return the entire message as a fallback
            return message.strip()

def extract_package_id(message):
    # Use regex to extract numbers following 'id' or 'package id'
    match = re.search(r'\b(?:id|package id)\s*(\d+)', message, re.IGNORECASE)
    if match:
        return match.group(1)
    else:
        return None

def extract_package_name(message):
    # Extract the package name after phrases like 'tell me more about'
    match = re.search(r'(?:tell me more about|show me details of|i want to know about)\s+(.*)', message, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    else:
        return message.strip()
