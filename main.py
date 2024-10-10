import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import openai
import requests
import spacy
from geopy.geocoders import Nominatim
import re

app = FastAPI()

# Set your OpenAI API key
openai.api_key = ''

# Set your Google API key
GOOGLE_API_KEY = ''

# Load the NLP model for English
nlp = spacy.load("en_core_web_sm")

# Serve static files (like your HTML) from a "static" directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up logging
logging.basicConfig(level=logging.INFO)

# Serve the HTML file from the root URL
@app.get("/", response_class=HTMLResponse)
async def serve_html():
    with open("static/index.html", "r") as f:
        return f.read()

# Create a request model for chat messages
class ChatMessageRequest(BaseModel):
    threadId: str
    message: str

# Helper function to get latitude and longitude using Google Geocoding API
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

# Helper function to get the timezone using Google Time Zone API
def get_timezone(lat, lng):
    timestamp = 0  # Current timestamp (can use int(time.time()) for current epoch time)
    timezone_url = f"https://maps.googleapis.com/maps/api/timezone/json?location={lat},{lng}&timestamp={timestamp}&key={GOOGLE_API_KEY}"
    response = requests.get(timezone_url)
    if response.status_code == 200:
        data = response.json()
        logging.info(f"Timezone ID: {data['timeZoneId']}")
        return data['timeZoneId']
    logging.error(f"Error fetching timezone for {lat}, {lng}")
    return None

# Helper function to fetch prayer times using Aladhan API
def get_prayer_times(city, country, specific_prayer=None):
    try:
        # Get latitude and longitude
        lat, lng = get_lat_long(city, country)
        if not lat or not lng:
            return "Could not find the location."

        # Fetch timezone using Google Time Zone API
        timezone = get_timezone(lat, lng)
        if not timezone:
            return "Could not retrieve the timezone."

        logging.info(f"Fetching prayer times for city: {city}, country: {country} in timezone {timezone}")

        # Aladhan API URL with the correct timezone
        api_url = f"https://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method=3&timezone={timezone}"
        response = requests.get(api_url)

        if response.status_code == 200:
            data = response.json()
            timings = data['data']['timings']

            # If a specific prayer is requested
            if specific_prayer:
                specific_time = timings.get(specific_prayer.capitalize())  # Capitalize to match the keys
                logging.info(f"Specific prayer time ({specific_prayer}): {specific_time}")
                return specific_time or f"{specific_prayer} time not available."
            else:
                # Format the output with bold text and emojis
                formatted_timings = (
                    f"**🕌 Here are the prayer times for {city}, {country}:**\n\n"
                    f"**Fajr** ⏰: {timings['Fajr']}\n"
                    f"**Dhuhr** ⏰: {timings['Dhuhr']}\n"
                    f"**Asr** ⏰: {timings['Asr']}\n"
                    f"**Maghrib** ⏰: {timings['Maghrib']}\n"
                    f"**Isha** ⏰: {timings['Isha']}\n"
                )
                return formatted_timings
        else:
            return "Sorry, I couldn't fetch the prayer times at the moment."
    except Exception as e:
        logging.error(f"Error fetching prayer times: {e}")
        return f"Error fetching prayer times: {e}"


# Function to extract locations using spaCy
def extract_location(message):
    doc = nlp(message)
    locations = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
    return locations

# Function to detect city and country
def detect_city_country(locations):
    # Use Google Geocoding API to detect the city and country
    for loc in locations:
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={loc}&key={GOOGLE_API_KEY}"
        response = requests.get(geocode_url)
        if response.status_code == 200:
            data = response.json()
            if len(data['results']) > 0:
                address_components = data['results'][0]['address_components']
                city = None
                country = None

                for component in address_components:
                    if "locality" in component["types"]:  # Checks for city/locality
                        city = component["long_name"]
                    if "country" in component["types"]:  # Checks for country
                        country = component["long_name"]

                # Special case where city and country might be the same, like "Singapore, Singapore"
                if not city and country and country.lower() == loc.lower():
                    city = country  # If no city is detected, assume it's the same as the country (like Singapore)

                if city and country:
                    return city, country

    return None, None



@app.post("/chat")
async def chat(request: ChatMessageRequest):
    specific_prayers = ["fajr", "dhuhr", "asr", "maghrib", "isha"]

    logging.info(f"Received message: {request.message} with threadId: {request.threadId}")

    # Create a flexible regex pattern to detect variations of "prayer time(s)"
    prayer_time_pattern = re.compile(r'\bprayer\s*time(?:s)?\b', re.IGNORECASE)

    if prayer_time_pattern.search(request.message.lower()) or any(prayer in request.message.lower() for prayer in specific_prayers):
        # Use spaCy to extract potential locations
        locations = extract_location(request.message)
        logging.info(f"Extracted locations: {locations}")

        if locations:
            # Detect city and country using extracted locations
            city, country = detect_city_country(locations)
            logging.info(f"Detected city: {city}, country: {country}")

            if city and country:
                specific_prayer = None
                for prayer in specific_prayers:
                    if prayer in request.message.lower():
                        specific_prayer = prayer
                        break

                # Fetch prayer times since city and country were detected
                prayer_times = get_prayer_times(city, country, specific_prayer)

                bot_reply = f"Here are the prayer times for {city}, {country}:\n\n{prayer_times}"
            else:
                bot_reply = "Sorry, I couldn't detect a valid city and country from your message."
        else:
            bot_reply = "Please specify the city and country for which you want the prayer times. For example, you can ask: 'What are the prayer times in Mumbai, India today?'"
    else:
        # Default response when no location or prayer times are detected
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": """
                You are Farah, a helpful, friendly, and informative assistant for Muslim travelers on a Muslim-friendly website (Halaltrip.com), focusing on providing tailored travel information while incorporating Islamic greetings and phrases to foster a welcoming atmosphere. when answering their questions, make it concise, format it nicely so that its appealing to the user.
                """},
                {"role": "user", "content": request.message}
            ]
        )
        bot_reply = response['choices'][0]['message']['content']

    logging.info(f"Bot reply: {bot_reply}")

    return {"bot_reply": bot_reply, "threadId": request.threadId}
