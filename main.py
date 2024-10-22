import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import openai
import requests
import spacy
import re
import docx  # Library to handle .docx files
import numpy as np
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# Set your OpenAI API key
openai.api_key = ''

# Set your Google API key
GOOGLE_API_KEY = ''  

# Set your Halaltrip API credentials
HALALTRIP_API_KEY = ''  
HALALTRIP_API_SECRET = '' 
HALALTRIP_TOKEN = ''

# # Generate TOKEN if not already generated
# import hashlib
# HALALTRIP_TOKEN = hashlib.md5((HALALTRIP_API_KEY + HALALTRIP_API_SECRET).encode('utf-8')).hexdigest()

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

# Helper function to fetch prayer times using Halaltrip API
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

# Helper function to fetch restaurants using Halaltrip API
def get_restaurants(city, country, cuisine=None):
    try:
        logging.info(f"Fetching restaurants for city: {city}, country: {country}, cuisine: {cuisine}")

        api_url = f"http://api.halaltrip.com/v1/api/restaurants"
        headers = {
            'APIKEY': HALALTRIP_API_KEY,
            'TOKEN': HALALTRIP_TOKEN
        }

        all_restaurants = []
        page = 1
        max_pages = 5  # Adjust as needed
        while page <= max_pages:
            params = {'page': page}
            response = requests.get(api_url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                restaurants = data.get('data', [])
                if not restaurants:
                    break  # No more restaurants
                all_restaurants.extend(restaurants)
                page += 1
            else:
                logging.error(f"Error fetching restaurants: {response.status_code} - {response.text}")
                return "Sorry, I couldn't fetch the list of restaurants at the moment."

        # Now filter restaurants by city and cuisine
        matched_restaurants = []
        for restaurant in all_restaurants:
            # Safely get the city information
            city_info = restaurant.get('city')
            if city_info and isinstance(city_info, dict):
                restaurant_city = city_info.get('name', '').strip().lower()
            else:
                restaurant_city = ''

            # Safely get the country information
            country_info = restaurant.get('country')
            if country_info and isinstance(country_info, dict):
                restaurant_country = country_info.get('name', '').strip().lower()
            else:
                restaurant_country = ''

            # Safely get the cuisine information
            restaurant_cuisine = restaurant.get('cuisine', '')
            if restaurant_cuisine:
                restaurant_cuisine = restaurant_cuisine.strip().lower()
            else:
                restaurant_cuisine = ''

            logging.debug(f"Comparing restaurant city '{restaurant_city}' with '{city.lower()}' and country '{restaurant_country}' with '{country.lower()}'")

            if restaurant_city == city.lower() and restaurant_country == country.lower():
                if cuisine:
                    if cuisine.lower() in restaurant_cuisine:
                        matched_restaurants.append(restaurant)
                else:
                    matched_restaurants.append(restaurant)

        if not matched_restaurants:
            if cuisine:
                return f"No halal {cuisine} restaurants found in {city}, {country}."
            else:
                return f"No halal restaurants found in {city}, {country}."

        # Format the response
        response_text = f"**🍽️ Here are some halal restaurants in {city}, {country}"
        if cuisine:
            response_text += f" serving {cuisine} cuisine"
        response_text += ":**\n\n"

        for i, restaurant in enumerate(matched_restaurants[:5]):  # Show top 5 restaurants
            name = restaurant.get('restaurantname', 'N/A').strip()
            address = restaurant.get('address', 'N/A').strip()
            restaurant_cuisine = restaurant.get('cuisine', 'N/A').strip()
            response_text += f"{i+1}. **{name}**\n   📍 Address: {address}\n   🍴 Cuisine: {restaurant_cuisine}\n\n"
        return response_text
    except Exception as e:
        logging.error(f"Error fetching restaurants: {e}")
        return f"Error fetching restaurants: {e}"



# Function to extract locations using spaCy
def extract_location(message):
    doc = nlp(message)
    locations = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
    return locations

# Function to detect city and country
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

# Helper function to read .docx files
def read_word_doc(filepath):
    doc = docx.Document(filepath)
    full_text = []
    for paragraph in doc.paragraphs:
        full_text.append(paragraph.text)
    return "\n".join(full_text)

# Helper function to create embeddings for the documents
def create_embeddings_for_docs():
    folder_path = "static/files"
    doc_embeddings = []
    filenames = []

    for filename in os.listdir(folder_path):
        if filename.endswith(".docx"):
            filepath = os.path.join(folder_path, filename)
            doc_content = read_word_doc(filepath)
            embedding = get_embedding(doc_content)
            logging.info(f"Created embedding for {filename}")  # Log the embedding creation
            doc_embeddings.append(embedding)
            filenames.append(filepath)

    return doc_embeddings, filenames

# Function to get embeddings using OpenAI's API
def get_embedding(text):
    response = openai.Embedding.create(
        input=[text],
        model="text-embedding-ada-002"
    )
    return response['data'][0]['embedding']

# Function to compute cosine similarity between two vectors
def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# Function to find the most relevant document using cosine similarity
def find_most_relevant_doc(query_embedding, doc_embeddings, filenames):
    similarities = []
    for idx, doc_embedding in enumerate(doc_embeddings):
        similarity = cosine_similarity(query_embedding, doc_embedding)
        similarities.append(similarity)
        logging.info(f"Similarity with {filenames[idx]}: {similarity}")  # Log similarity scores
    most_similar_idx = np.argmax(similarities)
    logging.info(f"Most similar document: {filenames[most_similar_idx]} with similarity {similarities[most_similar_idx]}")
    return filenames[most_similar_idx], similarities[most_similar_idx]

# Search through all .docx files in the static/files directory for relevant content using embeddings
def search_all_docs(query):
    # Create embeddings for documents (should be cached in production)
    doc_embeddings, filenames = create_embeddings_for_docs()
    # Get embedding for the query
    query_embedding = get_embedding(query)
    # Find the most relevant document
    most_relevant_filename, similarity = find_most_relevant_doc(query_embedding, doc_embeddings, filenames)
    logging.info(f"Most relevant document: {most_relevant_filename} with similarity {similarity}")

    # Set a similarity threshold
    SIMILARITY_THRESHOLD = 0.84  # Adjust this threshold as needed

    if similarity < SIMILARITY_THRESHOLD:
        logging.info(f"Similarity {similarity} is below threshold {SIMILARITY_THRESHOLD}. No relevant document found.")
        return None  # No relevant content found
    else:
        # Read content from the most relevant document
        relevant_content = read_word_doc(most_relevant_filename)
        return relevant_content

@app.post("/chat_with_file")
async def chat_with_file(request: ChatMessageRequest):
    query = request.message.strip()

    # Search the document for relevant content
    relevant_content = search_all_docs(query)

    if relevant_content and relevant_content.strip():  # Ensure relevant_content is not empty
        # If document content is found, log and use it
        logging.info(f"Information retrieved from document: {relevant_content}")

        # Send the document content along with the query to OpenAI to craft a response
        messages = [
            {
                "role": "system",
                "content": """
You are Farah, a helpful assistant for Muslim travelers on a Muslim-friendly website (Halaltrip.com). Use the provided document as a reference for your response. Cite information directly from the document, and mention that it comes from the provided content. Do not include any information that is not in the document. Use the provided document to answer the user's question as accurately as possible. Answer in a concise manner, well formatted, and make it look appealing. Feel free to use emojis.
"""
            },
            {
                "role": "user",
                "content": f"The following document is provided as reference:\n\n{relevant_content}"
            },
            {
                "role": "user",
                "content": f"Based on this document, please answer the following question:\n\n{request.message}"
            }
        ]

        logging.info(f"Messages sent to OpenAI API: {messages}")

        # Get a response from OpenAI based on the document
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages
        )
        bot_reply = response['choices'][0]['message']['content']
        logging.info("Response generated using document content.")
        return {"bot_reply": bot_reply, "threadId": request.threadId}

    else:
        # No relevant content found in documents, log it and trigger fallback to /chat
        logging.info("No relevant information found in documents. Falling back to /chat.")

        # Explicitly call the /chat logic
        response = await chat(request)  # Call the /chat logic
        return response  # Return the general /chat response

# Default chat endpoint
@app.post("/chat")
async def chat(request: ChatMessageRequest):
    specific_prayers = ["fajr", "dhuhr", "asr", "maghrib", "isha"]

    logging.info(f"Received message: {request.message} with threadId: {request.threadId}")

    # Patterns to detect the intent
    restaurant_pattern = re.compile(r'\b(restaurant|restaurants|food|eat)\b', re.IGNORECASE)
    prayer_time_pattern = re.compile(r'\bprayer\s*time(?:s)?\b', re.IGNORECASE)

    if restaurant_pattern.search(request.message.lower()):
        # Handle restaurant queries
        locations = extract_location(request.message)
        logging.info(f"Extracted locations: {locations}")

        if locations:
            city, country = detect_city_country(locations)
            logging.info(f"Detected city: {city}, country: {country}")

            if city and country:
                restaurants_info = get_restaurants(city, country)
                bot_reply = restaurants_info
            else:
                bot_reply = "Sorry, I couldn't detect a valid city and country from your message."
        else:
            bot_reply = "Please specify the city and country for which you want the list of restaurants. For example, you can ask: 'What are some halal restaurants in Singapore?'"

    elif prayer_time_pattern.search(request.message.lower()) or any(prayer in request.message.lower() for prayer in specific_prayers):
        locations = extract_location(request.message)
        logging.info(f"Extracted locations: {locations}")

        if locations:
            city, country = detect_city_country(locations)
            logging.info(f"Detected city: {city}, country: {country}")

            if city and country:
                specific_prayer = None
                for prayer in specific_prayers:
                    if prayer in request.message.lower():
                        specific_prayer = prayer
                        break

                prayer_times = get_prayer_times(city, country, specific_prayer)
                if specific_prayer:
                    bot_reply = f"The time for **{specific_prayer.capitalize()}** prayer in {city}, {country} is:\n\n{prayer_times}"
                else:
                    bot_reply = prayer_times  # `get_prayer_times` already returns formatted timings
            else:
                bot_reply = "Sorry, I couldn't detect a valid city and country from your message."
        else:
            bot_reply = "Please specify the city and country for which you want the prayer times. For example, you can ask: 'What are the prayer times in Mumbai, India today?'"

    else:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": """
You are Farah, a helpful, friendly, and informative assistant for Muslim travelers on a Muslim-friendly website (Halaltrip.com), focusing on providing tailored travel information while incorporating Islamic greetings and phrases to foster a welcoming atmosphere. When answering their questions, make it concise and format it nicely so that it's appealing to the user.
"""
                },
                {"role": "user", "content": request.message}
            ]
        )
        bot_reply = response['choices'][0]['message']['content']

    logging.info(f"Bot reply: {bot_reply}")

    return {"bot_reply": bot_reply, "threadId": request.threadId}
