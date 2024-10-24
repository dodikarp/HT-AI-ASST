# helpers.py

import os
import requests
import logging
import spacy
from spacy.matcher import Matcher
from dotenv import load_dotenv
import docx  # Library to handle .docx files

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
        'qibla', 'direction', 'halal', 'near', 'in', 'at', 'the', 'list', 'show', 'find', 'display'
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
