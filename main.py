# main.py

import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import openai
from dotenv import load_dotenv

# Import helper functions
from get_prayer_times import get_prayer_times
from get_restaurants import get_restaurants, get_restaurants_nearby
from get_mosques import get_mosques
from get_inflight_prayer_times import get_inflight_prayer_times  # Imported for inflight prayer times
from helpers import extract_location, detect_city_country, extract_flight_details  # Added extract_flight_details
from embeddings import search_all_docs

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the HTML file from the root URL
@app.get("/", response_class=HTMLResponse)
async def serve_html():
    with open("static/index.html", "r") as f:
        return f.read()

# Set OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

# Create a request model for chat messages
class ChatMessageRequest(BaseModel):
    threadId: str
    message: str
    # Latitude and longitude are optional and used for 'near me' features
    latitude: float = None
    longitude: float = None

# Function to check if input is acceptable using OpenAI's Moderation API
def is_input_acceptable(user_input):
    response = openai.Moderation.create(input=user_input)
    flagged = response['results'][0]['flagged']
    return not flagged  # Returns True if input is acceptable

# Intent classification function using GPT-4
def classify_intent_with_gpt(user_message):
    prompt = f"""
You are an AI assistant that classifies user messages into specific intents. Here are some examples:

User Message: "Hi"
Intent: greeting

User Message: "Hello there"
Intent: greeting

User Message: "List 5 mosques in Bedok Singapore"
Intent: mosque_query

User Message: "Mosques near me"
Intent: mosque_near_me

User Message: "Show me halal restaurants in Kuala Lumpur"
Intent: restaurant_query

User Message: "What are the prayer times in Dubai"
Intent: prayer_time_query

User Message: "Tell me more about Masjid Al-Ansar"
Intent: more_info

User Message: "Where is the nearest halal restaurant?"
Intent: restaurant_near_me

User Message: "Find mosques nearby"
Intent: mosque_near_me

User Message: "What is the Qibla direction?"
Intent: qibla_direction

User Message: "Are there any halal Thai restaurants in Bangkok?"
Intent: restaurant_cuisine_query

User Message: "Does Muslim Restaurant offer delivery services?"
Intent: restaurant_service_query

User Message: "What are the opening hours of Muslim Restaurant in Bangkok?"
Intent: restaurant_operating_hours_query

User Message: "I'm looking for a halal restaurant in Bangkok to celebrate a special occasion."
Intent: restaurant_special_request

User Message: "What's the square root of a banana?"
Intent: out_of_scope

User Message: "Tell me a joke about flying elephants"
Intent: out_of_scope

User Message: "Can you provide inflight prayer times from SIN to DEL on 28-02-2019?"
Intent: inflight_prayer_times

User Message: "I need inflight prayer times for my flight from JFK to LHR."
Intent: inflight_prayer_times

User Message: "{user_message}"
Intent:"""

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=10,
        n=1,
        stop=["\n"],
        temperature=0
    )
    intent = response.choices[0].message['content'].strip().lower()
    return intent

# Default chat endpoint
@app.post("/chat")
async def chat(request: ChatMessageRequest):
    logging.info(f"Received message: {request.message} with threadId: {request.threadId}")
    message = request.message.strip()

    # Check if the input is acceptable
    if not is_input_acceptable(message):
        bot_reply = "I'm sorry, but I can't assist with that request."
        logging.info("User input was flagged by Moderation API.")
        return {"bot_reply": bot_reply, "threadId": request.threadId}

    # Classify the intent using GPT-4
    intent = classify_intent_with_gpt(message)
    logging.info(f"Classified intent: {intent}")

    bot_reply = "I'm sorry, I didn't quite understand that. Could you please rephrase your request?"

    try:
        if intent == 'greeting':
            bot_reply = "👋 Assalamu Alaikum! I'm Farah, your assistant for Muslim-friendly travel. I can help with finding halal restaurants, mosques, prayer times, and inflight prayer times. How may I assist you today?"

        elif intent == 'more_info':
            # Pass the message to GPT-4 for detailed information
            logging.info("User is requesting more information. Passing to GPT-4.")
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": """
You are Farah, a helpful, friendly, and informative assistant for Muslim travelers on a Muslim-friendly website (Halaltrip.com). When providing information about specific places like mosques or restaurants, include historical context, specialties, unique features, and any details that might interest travelers.
"""
                    },
                    {"role": "user", "content": message}
                ]
            )
            bot_reply = response['choices'][0]['message']['content']

        elif intent == 'qibla_direction':
            bot_reply = "You can find the Qibla direction here: [Qibla Direction](https://www.halaltrip.com/prayertimes/qibla-direction)."

        elif intent == 'mosque_near_me':
            # Handle 'near me' mosque queries
            logging.info("User is requesting mosques near them.")
            if request.latitude is not None and request.longitude is not None:
                # Use the user's latitude and longitude
                latitude = request.latitude
                longitude = request.longitude
                logging.info(f"User's location: Latitude {latitude}, Longitude {longitude}")

                radius = 5  # Default radius in kilometers

                mosques_info = get_mosques(latitude=latitude, longitude=longitude, radius=radius)
                bot_reply = mosques_info
            else:
                bot_reply = "Please enable location services or provide your latitude and longitude to find mosques near you."

        elif intent == 'restaurant_near_me':
            # Handle 'near me' restaurant queries
            logging.info("User is requesting restaurants near them.")
            if request.latitude is not None and request.longitude is not None:
                # Use the user's latitude and longitude
                latitude = request.latitude
                longitude = request.longitude
                logging.info(f"User's location: Latitude {latitude}, Longitude {longitude}")

                radius = 5  # Default radius in kilometers

                # Optionally, extract cuisine from the message
                cuisine = None  # Implement extraction if needed

                restaurants_info = get_restaurants_nearby(latitude=latitude, longitude=longitude, radius=radius, cuisine=cuisine)
                bot_reply = restaurants_info
            else:
                bot_reply = "Please enable location services or provide your latitude and longitude to find halal restaurants near you."

        elif intent == 'restaurant_query':
            # Handle general restaurant queries
            locations = extract_location(message)
            logging.info(f"Extracted locations: {locations}")

            # Optionally, extract cuisine from the message
            cuisine = None  # Implement extraction if needed

            if locations:
                area = ' '.join(locations)
                logging.info(f"Detected area: {area}")

                # Extract city and country from area
                city, country = detect_city_country([area])
                if city or country:
                    restaurants_info = get_restaurants(area=area, city=city, country=country, cuisine=cuisine)
                    bot_reply = restaurants_info
                else:
                    bot_reply = f"Couldn't determine the city and country from '{area}'. Please provide more specific information."
            else:
                bot_reply = "Please specify the area or location for which you want the list of halal restaurants."

        elif intent == 'restaurant_cuisine_query':
            # Handle restaurant queries with cuisine
            locations = extract_location(message)
            logging.info(f"Extracted locations: {locations}")

            # Extract cuisine from the message
            # Implement a function to extract cuisine, or extract it here
            cuisine_keywords = ['thai', 'indian', 'malay', 'vegetarian', 'chinese', 'italian']
            cuisine = None
            for keyword in cuisine_keywords:
                if keyword.lower() in message.lower():
                    cuisine = keyword
                    break

            if locations:
                area = ' '.join(locations)
                logging.info(f"Detected area: {area}")

                # Extract city and country from area
                city, country = detect_city_country([area])
                if city or country:
                    restaurants_info = get_restaurants(area=area, city=city, country=country, cuisine=cuisine)
                    bot_reply = restaurants_info
                else:
                    bot_reply = f"Couldn't determine the city and country from '{area}'. Please provide more specific information."
            else:
                bot_reply = "Please specify the area or location for which you want the list of halal restaurants."

        elif intent == 'restaurant_service_query':
            # Handle inquiries about restaurant services (e.g., delivery)
            bot_reply = "As of my current information, there's no specific mention of delivery services. I recommend contacting the restaurant directly to inquire about delivery options."

        elif intent == 'restaurant_operating_hours_query':
            # Handle inquiries about operating hours
            bot_reply = "I'm sorry, but I don't have the current operating hours for that restaurant. I recommend visiting their official website or contacting them directly for the most up-to-date information."

        elif intent == 'restaurant_special_request':
            # Handle special requests, e.g., for celebrations
            # Provide recommendations
            locations = extract_location(message)
            logging.info(f"Extracted locations: {locations}")

            if locations:
                area = ' '.join(locations)
                logging.info(f"Detected area: {area}")

                city, country = detect_city_country([area])
                if city or country:
                    # Optionally, filter for restaurants suitable for special occasions
                    # For now, we can just call get_restaurants
                    restaurants_info = get_restaurants(area=area, city=city, country=country)
                    bot_reply = f"Here are some recommendations for your special occasion:\n\n{restaurants_info}"
                else:
                    bot_reply = f"Couldn't determine the city and country from '{area}'. Please provide more specific information."
            else:
                bot_reply = "Please specify the area or location where you're looking to celebrate."

        elif intent == 'prayer_time_query':
            # Handle prayer time queries
            locations = extract_location(message)
            logging.info(f"Extracted locations: {locations}")

            specific_prayers = ["fajr", "dhuhr", "asr", "maghrib", "isha"]
            specific_prayer = None
            for prayer in specific_prayers:
                if prayer in message.lower():
                    specific_prayer = prayer
                    break

            if locations:
                area = ' '.join(locations)
                logging.info(f"Detected area: {area}")

                city, country = detect_city_country([area])
                if city and country:
                    prayer_times = get_prayer_times(city=city, country=country, specific_prayer=specific_prayer)
                    if specific_prayer:
                        bot_reply = f"The time for **{specific_prayer.capitalize()}** prayer in {city}, {country} is:\n\n{prayer_times}"
                    else:
                        bot_reply = prayer_times
                else:
                    bot_reply = f"Couldn't determine the city and country from '{area}'. Please provide more specific information."
            else:
                bot_reply = "Please specify the area or location for which you want the prayer times."

        elif intent == 'inflight_prayer_times':
            # Handle inflight prayer times queries
            logging.info("User is requesting inflight prayer times.")
            # Extract flight details from the message
            flight_details = extract_flight_details(message)
            if flight_details:
                departureAP = flight_details['departureAP']
                departureDateTime = flight_details['departureDateTime']
                arrivalAP = flight_details['arrivalAP']
                arrivalDateTime = flight_details['arrivalDateTime']

                prayer_times_info = get_inflight_prayer_times(
                    departureAP=departureAP,
                    departureDateTime=departureDateTime,
                    arrivalAP=arrivalAP,
                    arrivalDateTime=arrivalDateTime
                )
                bot_reply = prayer_times_info
            else:
                bot_reply = "Please provide your departure airport code, departure date and time, arrival airport code, and arrival date and time in the format:\n\n- Departure Airport Code (IATA):\n- Departure Date and Time (dd-mm-yyyy HH:MM):\n- Arrival Airport Code (IATA):\n- Arrival Date and Time (dd-mm-yyyy HH:MM)"

        elif intent == 'out_of_scope':
            # Handle out-of-scope or ridiculous questions
            bot_reply = "I'm sorry, but I can assist you with information on halal restaurants, mosques, prayer times, inflight prayer times, and travel-related queries. How may I help you today?"

        else:
            # Default response using OpenAI GPT
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": """
You are Farah, a helpful, friendly, and informative assistant for Muslim travelers on a Muslim-friendly website (Halaltrip.com), focusing on providing tailored travel information while incorporating Islamic greetings and phrases to foster a welcoming atmosphere. When answering their questions, make it concise and format it nicely so that it's appealing to the user.
"""
                    },
                    {"role": "user", "content": message}
                ]
            )
            bot_reply = response['choices'][0]['message']['content']

    except Exception as e:
        logging.error(f"Error handling intent '{intent}': {e}")
        bot_reply = "I'm sorry, something went wrong while processing your request."

    logging.info(f"Bot reply: {bot_reply}")
    return {"bot_reply": bot_reply, "threadId": request.threadId}

# Chat with file endpoint
@app.post("/chat_with_file")
async def chat_with_file(request: ChatMessageRequest):
    query = request.message.strip()

    # Check if the input is acceptable
    if not is_input_acceptable(query):
        bot_reply = "I'm sorry, but I can't assist with that request."
        logging.info("User input was flagged by Moderation API.")
        return {"bot_reply": bot_reply, "threadId": request.threadId}

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
