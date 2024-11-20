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
import re
import difflib

# Import helper functions
from get_prayer_times import get_prayer_times
from get_restaurants import (
    get_restaurants,
    get_restaurants_nearby,
    get_restaurant_by_name,
    get_restaurant_by_exact_name
)
from get_mosques import get_mosques
from get_inflight_prayer_times import get_inflight_prayer_times
from helpers import (
    extract_location,
    detect_city_country,
    extract_flight_details,
    extract_restaurant_name,
    extract_keyword,
    extract_package_id,
    extract_package_name
)
from embeddings import search_all_docs
from get_packages import get_all_packages, get_package_by_id, search_packages_by_keyword

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
def classify_intent_with_gpt(user_message, previous_intent=None):
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

User Message: "Tell me more about Muslim Restaurant in Bangkok"
Intent: restaurant_detail_query

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

User Message: "Can you provide inflight prayer times from SIN to DEL on 28-02-2019?"
Intent: inflight_prayer_times

User Message: "I need inflight prayer times for my flight from JFK to LHR."
Intent: inflight_prayer_times

User Message: "Can you show me travel packages to Bosnia?"
Intent: package_query

User Message: "Tell me more about package ID 420"
Intent: package_detail_query

User Message: "I'd like to know about the Bosnian Odyssey package."
Intent: package_detail_query

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

    # If previous intent was expecting a package detail
    if previous_intent == 'package_query' and intent == 'package_detail_query':
        return 'package_detail_query'

    # If previous intent was restaurant_detail_query and bot is expecting a restaurant name
    if previous_intent == 'restaurant_detail_query' and intent == 'restaurant_detail_query':
        return 'restaurant_name_provided'

    return intent

# Global dictionary to hold conversation states
conversation_states = {}

# Welcome endpoint
@app.get("/welcome")
async def welcome():
    welcome_message = """
👋 **Assalamu Alaikum!**

I'm **Farah**, your friendly assistant for Muslim-friendly travel. I'm here to help make your journey comfortable and enriching. Here's what I can assist you with:

- **🍽️ Finding Halal Restaurants**
  - *Examples:*
    - "Halal restaurants near me"

- **🕌 Locating Mosques**
  - *Examples:*
    - "Where is the nearest mosque?"
    - "List mosques near me."
    - "Mosques in Singapore"

- **🕋 Providing Prayer Times**
  - *Examples:*
    - "What are the prayer times in Dubai?"
    - "When is Maghrib prayer in London?"
    - "Prayer times in Jakarta today."

- **✈️ Inflight Prayer Times**
  - *Examples:*
    - "Can you provide inflight prayer times from SIN to DEL on 28-02-2023?"
    - "I need inflight prayer times for my flight from JFK to LHR."

- **🧭 Qibla Direction**
  - *Example:*
    - "What is the Qibla direction from my location?"

- **🧳 Travel Packages**
  - *Examples:*
    - "Can you show me travel packages to Bosnia?"
    - "Tell me more about package ID 420."

- **📝 Additional Information**
  - *Examples:*
    - "Tell me more about Muslim Restaurant in Bangkok."
    - "What is Qiyam"

Feel free to ask me anything related to your Muslim-friendly travel needs. How may I assist you today?
"""
    return {"bot_reply": welcome_message}

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

    # Get or initialize the conversation state for this threadId
    state = conversation_states.get(request.threadId, {'last_intent': None, 'data': {}})

    # Classify the intent using GPT-4
    intent = classify_intent_with_gpt(message, previous_intent=state['last_intent'])
    logging.info(f"Classified intent: {intent}")

    bot_reply = "I'm sorry, I didn't quite understand that. Could you please rephrase your request?"

    try:
        if intent == 'greeting':
            bot_reply = "👋 Assalamu Alaikum! I'm Farah, your assistant for Muslim-friendly travel. I can help with finding halal restaurants, mosques, prayer times, inflight prayer times, and travel packages. How may I assist you today?"
            state['data'] = {}  # Reset state data

        elif intent == 'package_query':
            # Handle general package queries
            keyword = extract_keyword(message)
            if keyword:
                packages = search_packages_by_keyword(keyword)
                if packages:
                    bot_reply = "Here are some packages that match your search:\n\n"
                    for package in packages[:5]:  # Limit to 5 packages
                        bot_reply += f"- **{package.get('name', 'N/A')}** (ID: {package.get('id', 'N/A')})\n"
                    bot_reply += "\nPlease let me know if you'd like more details on any of these packages."
                    # Store the list of package IDs in the conversation state
                    state['data']['expected_packages'] = [pkg.get('id') for pkg in packages]
                else:
                    # If no packages match, provide available packages
                    all_packages = get_all_packages()
                    if all_packages:
                        bot_reply = "Sorry, I couldn't find any packages matching your search. Here are some available packages:\n\n"
                        for package in all_packages[:5]:
                            bot_reply += f"- **{package.get('name', 'N/A')}** (ID: {package.get('id', 'N/A')})\n"
                        bot_reply += "\nPlease let me know if any of these interest you."
                    else:
                        bot_reply = "Sorry, I couldn't retrieve the packages at this time."
            else:
                # If no keyword is extracted, list available packages
                packages = get_all_packages()
                if packages:
                    bot_reply = "Here are some available packages:\n\n"
                    for package in packages[:5]:
                        bot_reply += f"- **{package.get('name', 'N/A')}** (ID: {package.get('id', 'N/A')})\n"
                    bot_reply += "\nPlease let me know if you'd like more details on any of these packages."
                    state['data']['expected_packages'] = [pkg.get('id') for pkg in packages]
                else:
                    bot_reply = "Sorry, I couldn't retrieve the packages at this time."
            state['last_intent'] = intent






        elif intent == 'package_detail_query':
            # Handle package detail queries
            package_id = extract_package_id(message)
            if package_id:
                package = get_package_by_id(package_id)
                if package:
                    name = package.get('name', 'N/A')
                    description = package.get('description', 'No description available.')
                    price_info = package.get('prices', [])
                    if price_info:
                        price = f"{price_info[0].get('currency', 'USD')} {price_info[0].get('price_standard', 'N/A')}"
                    else:
                        price = 'Price information not available.'

                    bot_reply = f"**{name}**\n\n{description}\n\n**Price:** {price}\n\nWould you like to book this package?"
                    state['data']['expected_packages'] = None  # Clear expected packages
                else:
                    bot_reply = f"Sorry, I couldn't find a package with ID {package_id}."
            else:
                # If package ID is not provided, check if user selected from previous list
                if 'expected_packages' in state['data'] and state['data']['expected_packages']:
                    selected_package_name = extract_package_name(message).lower()
                    # Try to match the selected package name with the expected packages
                    matching_package_id = None
                    for pkg_id in state['data']['expected_packages']:
                        pkg = get_package_by_id(pkg_id)
                        if pkg:
                            package_name = pkg.get('name', '').lower()
                            # Use fuzzy matching
                            if selected_package_name == package_name:
                                matching_package_id = pkg_id
                                break
                            elif selected_package_name in package_name or package_name in selected_package_name:
                                matching_package_id = pkg_id
                                break
                            else:
                                # Use difflib for approximate matching
                                ratio = difflib.SequenceMatcher(None, selected_package_name, package_name).ratio()
                                if ratio > 0.7:
                                    matching_package_id = pkg_id
                                    break
                    if matching_package_id:
                        package = get_package_by_id(matching_package_id)
                        name = package.get('name', 'N/A')
                        description = package.get('description', 'No description available.')
                        price_info = package.get('prices', [])
                        if price_info:
                            price = f"{price_info[0].get('currency', 'USD')} {price_info[0].get('price_standard', 'N/A')}"
                        else:
                            price = 'Price information not available.'

                        bot_reply = f"**{name}**\n\n{description}\n\n**Price:** {price}\n\nWould you like to book this package?"
                        state['data']['expected_packages'] = None  # Clear expected packages
                    else:
                        bot_reply = "Please specify the package ID or name from the list provided."
                else:
                    bot_reply = "Please specify the package ID or name of the package you'd like to know more about."
            state['last_intent'] = intent








        elif intent == 'restaurant_detail_query':
            # Extract restaurant name from the message
            restaurant_name = extract_restaurant_name(message)
            if restaurant_name:
                # Get restaurant details by name
                restaurant_info = get_restaurant_by_name(restaurant_name)
                if restaurant_info:
                    bot_reply = restaurant_info
                    # Clear any previous expected restaurants
                    state['data']['expected_restaurants'] = None
                else:
                    # If multiple matches are found
                    if isinstance(restaurant_info, str) and restaurant_info.startswith("I found multiple restaurants"):
                        # Extract restaurant names from the response
                        restaurant_list = re.findall(r"\*\*(.*?)\*\*", restaurant_info)
                        # Store the list in the conversation state
                        state['data']['expected_restaurants'] = restaurant_list
                    bot_reply = restaurant_info
            else:
                bot_reply = "Please specify the name of the restaurant you'd like to know more about."
            state['last_intent'] = intent

        elif intent == 'restaurant_name_provided' and state['last_intent'] == 'restaurant_detail_query' and state['data'].get('expected_restaurants'):
            # The user is specifying the restaurant name from previous prompt
            restaurant_name = message.strip()
            expected_restaurants = state['data']['expected_restaurants']
            if restaurant_name in expected_restaurants:
                # Get the restaurant details
                restaurant_info = get_restaurant_by_exact_name(restaurant_name)
                if restaurant_info:
                    bot_reply = restaurant_info
                    # Clear the expected restaurants list
                    state['data']['expected_restaurants'] = None
                    state['last_intent'] = None  # Reset intent
                else:
                    bot_reply = f"Sorry, I couldn't find details for '{restaurant_name}'."
            else:
                bot_reply = "Please specify a restaurant from the list provided."
            state['last_intent'] = intent

        elif intent == 'qibla_direction':
            bot_reply = "You can find the Qibla direction here: [Qibla Direction](https://www.halaltrip.com/prayertimes/qibla-direction)."
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

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
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

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
                cuisine_keywords = ['thai', 'indian', 'malay', 'vegetarian', 'chinese', 'italian']
                cuisine = None
                for keyword in cuisine_keywords:
                    if keyword.lower() in message.lower():
                        cuisine = keyword
                        break

                restaurants_info = get_restaurants_nearby(latitude=latitude, longitude=longitude, radius=radius, cuisine=cuisine)
                bot_reply = restaurants_info
            else:
                bot_reply = "Please enable location services or provide your latitude and longitude to find halal restaurants near you."
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

        elif intent == 'restaurant_query':
            # Handle general restaurant queries
            locations = extract_location(message)
            logging.info(f"Extracted locations: {locations}")

            # Extract cuisine from the message
            cuisine_keywords = ['thai', 'indian', 'malay', 'vegetarian', 'chinese', 'italian']
            cuisine = None
            for keyword in cuisine_keywords:
                if keyword.lower() in message.lower():
                    cuisine = keyword
                    break

            if locations:
                # Combine locations to form area
                area = ', '.join(locations)
                logging.info(f"Detected area: {area}")

                # Try to detect city and country from locations
                city, country = detect_city_country(locations)
                if city or country:
                    restaurants_info = get_restaurants(area=area, city=city, country=country, cuisine=cuisine)
                    bot_reply = restaurants_info
                else:
                    # If city and country cannot be determined, proceed with area only
                    restaurants_info = get_restaurants(area=area, cuisine=cuisine)
                    bot_reply = restaurants_info
            else:
                bot_reply = "Please specify the area or location for which you want the list of halal restaurants."
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

        elif intent == 'restaurant_cuisine_query':
            # Handle restaurant queries with cuisine
            locations = extract_location(message)
            logging.info(f"Extracted locations: {locations}")

            # Extract cuisine from the message
            cuisine_keywords = ['thai', 'indian', 'malay', 'vegetarian', 'chinese', 'italian']
            cuisine = None
            for keyword in cuisine_keywords:
                if keyword.lower() in message.lower():
                    cuisine = keyword
                    break

            if locations:
                # Combine locations to form area
                area = ', '.join(locations)
                logging.info(f"Detected area: {area}")

                # Try to detect city and country from locations
                city, country = detect_city_country(locations)
                if city or country:
                    restaurants_info = get_restaurants(area=area, city=city, country=country, cuisine=cuisine)
                    bot_reply = restaurants_info
                else:
                    # If city and country cannot be determined, proceed with area only
                    restaurants_info = get_restaurants(area=area, cuisine=cuisine)
                    bot_reply = restaurants_info
            else:
                bot_reply = "Please specify the area or location for which you want the list of halal restaurants."
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

        elif intent == 'restaurant_service_query':
            # Handle inquiries about restaurant services (e.g., delivery)
            bot_reply = "As of my current information, there's no specific mention of delivery services. I recommend contacting the restaurant directly to inquire about delivery options."
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

        elif intent == 'restaurant_operating_hours_query':
            # Handle inquiries about operating hours
            bot_reply = "I'm sorry, but I don't have the current operating hours for that restaurant. I recommend visiting their official website or contacting them directly for the most up-to-date information."
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

        elif intent == 'restaurant_special_request':
            # Handle special requests, e.g., for celebrations
            # Provide recommendations
            locations = extract_location(message)
            logging.info(f"Extracted locations: {locations}")

            # Extract cuisine from the message
            cuisine_keywords = ['thai', 'indian', 'malay', 'vegetarian', 'chinese', 'italian']
            cuisine = None
            for keyword in cuisine_keywords:
                if keyword.lower() in message.lower():
                    cuisine = keyword
                    break

            if locations:
                # Combine locations to form area
                area = ', '.join(locations)
                logging.info(f"Detected area: {area}")

                city, country = detect_city_country(locations)
                if city or country:
                    # Optionally, filter for restaurants suitable for special occasions
                    restaurants_info = get_restaurants(area=area, city=city, country=country, cuisine=cuisine)
                    bot_reply = f"Here are some recommendations for your special occasion:\n\n{restaurants_info}"
                else:
                    # If city and country cannot be determined, proceed with area only
                    restaurants_info = get_restaurants(area=area, cuisine=cuisine)
                    bot_reply = f"Here are some recommendations for your special occasion:\n\n{restaurants_info}"
            else:
                bot_reply = "Please specify the area or location where you're looking to celebrate."
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

        elif intent == 'prayer_time_query':
            # Handle prayer time queries
            message_lower = message.lower()

            # List of specific prayers
            specific_prayers = ["fajr", "dhuhr", "asr", "maghrib", "isha"]
            specific_prayer = None

            # Implement fuzzy matching for prayer names
            words = message_lower.split()
            for word in words:
                close_matches = difflib.get_close_matches(word, specific_prayers, n=1, cutoff=0.7)
                if close_matches:
                    specific_prayer = close_matches[0]
                    # Remove the prayer name from the message
                    message_lower = message_lower.replace(word, '')
                    break

            # Extract locations from the modified message
            locations = extract_location(message_lower)
            logging.info(f"Extracted locations: {locations}")

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
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

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
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

        elif intent == 'out_of_scope':
            # Handle out-of-scope or ridiculous questions
            bot_reply = "I'm sorry, but I can assist you with information on halal restaurants, mosques, prayer times, inflight prayer times, travel packages, and travel-related queries. How may I help you today?"
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

        else:
            # Default response using OpenAI GPT
            bot_reply = generate_response_with_gpt(message)
            state['data'] = {}  # Reset state data
            state['last_intent'] = intent

    except Exception as e:
        logging.error(f"Error handling intent '{intent}': {e}")
        bot_reply = "I'm sorry, something went wrong while processing your request."

    logging.info(f"Bot reply: {bot_reply}")

    # Update the last intent
    state['last_intent'] = intent
    # Save the updated state
    conversation_states[request.threadId] = state

    return {"bot_reply": bot_reply, "threadId": request.threadId}

# Function to generate response with GPT-4
def generate_response_with_gpt(message):
    try:
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
        return bot_reply
    except Exception as e:
        logging.error(f"Error generating response with GPT-4: {e}")
        return "I'm sorry, I couldn't process your request at the moment."

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
