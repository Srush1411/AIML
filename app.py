import os
import threading
from flask import Flask, request, jsonify
from pymongo import MongoClient, errors
from bson import ObjectId
from dotenv import load_dotenv
# Import functions
from ratings_analysis import calculate_recommendations, sync_dish_rating, bulk_sync_all

# Load environment variables from .env file
load_dotenv()

# Initialize Flask App
app = Flask(__name__)

# --- DATABASE CONFIGURATION & OPTIMIZATION ---
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "Killa_db")

try:
    # OPTIMIZATION: Added maxPoolSize=50 to handle multiple concurrent requests efficiently
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, maxPoolSize=50)
    client.server_info() 
    db = client[DATABASE_NAME]
    print(f"Successfully connected to MongoDB Cluster. Database: {DATABASE_NAME}")
    
    # --- OPTIMIZATION: NON-BLOCKING AUTO-SYNC ---
    # Instead of making the server wait (and blocking traffic) while it calculates 
    # math for hundreds of past orders, we run this in a background daemon thread.
    def background_sync():
        print("Running initial bulk sync in background to catch up on existing ratings...")
        try:
            count = bulk_sync_all(db)
            print(f"Startup Sync Complete: {count} dishes updated with real ratings.")
        except Exception as e:
            print(f"Background Sync Error: {e}")

    # Start the background task
    threading.Thread(target=background_sync, daemon=True).start()
    
except Exception as err:
    print(f"CRITICAL ERROR: Could not connect to MongoDB. Details: {err}")
    db = None

@app.route('/aiml/recommend', methods=['POST'])
def recommend():
    """
    API Endpoint to fetch AI recommendations.
    """
    if db is None: return jsonify({"success": False, "error": "DB Offline"}), 503
    try:
        data = request.get_json() or {}
        user_id = data.get('userId')
        recommended_ids = calculate_recommendations(db, user_id)
        return jsonify({"success": True, "recommendations": recommended_ids}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/aiml/update-rating', methods=['POST'])
def update_rating():
    """
    MATCHED: Updated route to /update-rating to match Node.js Backend calls.
    Triggered when a user submits a new review from the Angular frontend.
    """
    if db is None: return jsonify({"success": False, "error": "DB Offline"}), 503
    try:
        data = request.get_json() or {}
        dish_id = data.get('dishId')
        if not dish_id:
            return jsonify({"success": False, "error": "dishId required"}), 400
            
        new_avg = sync_dish_rating(db, dish_id)
        return jsonify({"success": True, "newAverage": new_avg}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/aiml/bulk-sync', methods=['POST'])
def bulk_sync():
    """
    API Endpoint to manually force a global resync if needed.
    """
    if db is None: return jsonify({"success": False, "error": "DB Offline"}), 503
    try:
        count = bulk_sync_all(db)
        return jsonify({"success": True, "dishesUpdated": count}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "Killa AIML Engine Online", "database": DATABASE_NAME}), 200

if __name__ == '__main__':
    # OPTIMIZATION: Turning off debug mode when not in development increases speed
    # Threaded=True ensures Flask handles concurrent requests without bottlenecking
    flask_debug = os.getenv("FLASK_ENV") == "development"
    app.run(host='0.0.0.0', port=8000, debug=flask_debug, threaded=True)