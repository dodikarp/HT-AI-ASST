# embeddings.py

import os
import openai
import numpy as np
import logging
from dotenv import load_dotenv
from helpers import read_word_doc
import os

# Load environment variables
load_dotenv()

# Set OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

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

def get_embedding(text):
    response = openai.Embedding.create(
        input=[text],
        model="text-embedding-ada-002"
    )
    return response['data'][0]['embedding']

def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def find_most_relevant_doc(query_embedding, doc_embeddings, filenames):
    similarities = []
    for idx, doc_embedding in enumerate(doc_embeddings):
        similarity = cosine_similarity(query_embedding, doc_embedding)
        similarities.append(similarity)
        logging.info(f"Similarity with {filenames[idx]}: {similarity}")  # Log similarity scores
    most_similar_idx = np.argmax(similarities)
    logging.info(f"Most similar document: {filenames[most_similar_idx]} with similarity {similarities[most_similar_idx]}")
    return filenames[most_similar_idx], similarities[most_similar_idx]

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
