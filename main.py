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

# Helper function to fetch prayer times using Aladhan API
def get_prayer_times(city, country, specific_prayer=None):
    try:
        lat, lng = get_lat_long(city, country)
        if not lat or not lng:
            return "Could not find the location."

        timezone = get_timezone(lat, lng)
        if not timezone:
            return "Could not retrieve the timezone."

        logging.info(f"Fetching prayer times for city: {city}, country: {country} in timezone {timezone}")

        api_url = f"https://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method=3&timezone={timezone}"
        response = requests.get(api_url)

        if response.status_code == 200:
            data = response.json()
            timings = data['data']['timings']

            if specific_prayer:
                specific_time = timings.get(specific_prayer.capitalize())
                logging.info(f"Specific prayer time ({specific_prayer}): {specific_time}")
                return specific_time or f"{specific_prayer} time not available."
            else:
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
    for doc_embedding in doc_embeddings:
        similarity = cosine_similarity(query_embedding, doc_embedding)
        similarities.append(similarity)
    # Get the index of the most similar document
    most_similar_idx = np.argmax(similarities)
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
    # Read content from the most relevant document
    relevant_content = read_word_doc(most_relevant_filename)
    return relevant_content

# Endpoint to handle requests and use all .docx files for reference
@app.post("/chat_with_file")
async def chat_with_file(request: ChatMessageRequest):
    query = request.message.strip()
    relevant_content = search_all_docs(query)

    if relevant_content:
        # Log the messages being sent to the OpenAI API
        messages = [
            {
                "role": "system",
                "content": """
You are Farah, a helpful assistant for Muslim travelers on a Muslim-friendly website (Halaltrip.com). Use the provided document as a reference for your response. Cite information directly from the document, and mention that it comes from the provided content. Do not include any information that is not in the document. Use the provided document to answer the user's question as accurately as possible.
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

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages
        )
        bot_reply = response['choices'][0]['message']['content']
    else:
        # Handle case where no relevant content is found
        bot_reply = "I'm sorry, I couldn't find any information related to your question in the provided documents."

    logging.info(f"Bot reply: {bot_reply}")
    return {"bot_reply": bot_reply, "threadId": request.threadId}

# Default chat endpoint
@app.post("/chat")
async def chat(request: ChatMessageRequest):
    specific_prayers = ["fajr", "dhuhr", "asr", "maghrib", "isha"]

    logging.info(f"Received message: {request.message} with threadId: {request.threadId}")

    prayer_time_pattern = re.compile(r'\bprayer\s*time(?:s)?\b', re.IGNORECASE)

    if prayer_time_pattern.search(request.message.lower()) or any(prayer in request.message.lower() for prayer in specific_prayers):
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
                bot_reply = f"Here are the prayer times for {city}, {country}:\n\n{prayer_times}"
            else:
                bot_reply = "Sorry, I couldn't detect a valid city and country from your message."
        else:
            bot_reply = "Please specify the city and country for which you want the prayer times. For example, you can ask: 'What are the prayer times in Mumbai, India today?'"
    else:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
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
