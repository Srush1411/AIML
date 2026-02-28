import random
from flask import Flask, request, jsonify
from flask_cors import CORS
from collections import defaultdict
from textblob import TextBlob
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for communication with the Node.js backend

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/Killa_db")
DB_NAME = os.getenv("DATABASE_NAME", "Killa_db")

def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]

def get_sentiment(text):
    """
    NLP Logic: Analyzes polarity from -1.0 (very negative) to 1.0 (very positive).
    Includes manual keyword boost logic for restaurant-specific context.
    """
    if not text or len(text.strip()) < 3:
        return 0
    
    try:
        analysis = TextBlob(text)
        score = analysis.sentiment.polarity

        # Keyword Boost Logic: Manual correction for common restaurant terms
        text_lower = text.lower()
        
        # Positive Boosts
        if any(word in text_lower for word in ["best", "amazing", "legendary", "delicious", "excellent"]):
            score += 0.2
            
        # Negative Penalties
        if any(word in text_lower for word in ["cold", "late", "salty", "bad", "terrible", "worst"]):
            score -= 0.3
            
        return max(-1.0, min(1.0, score))  # Clamp between -1 and 1
    except:
        return 0

@app.route('/aiml/recommend', methods=['POST'])
def recommend():
    """
    AI Discovery Engine v2 (Sentiment Aware).
    Logic flow:
    1. Aggregate Sales Performance (50% weight)
    2. Process Granular Dish Ratings (30% weight)
    3. Process Review Tone via NLP Sentiment (20% weight)
    4. Mix in Discovery Items (New/Low sales)
    """
    try:
        db = get_db()
        data = request.get_json()
        user_id = data.get('userId')

        print("\n--- AI SENTIMENT ENGINE START ---")

        # Fetch Data from MongoDB
        all_food_items = list(db.menuitems.find({"isAvailable": True, "category": {"$ne": "drinks"}}))
        completed_orders = list(db.orders.find({"orderStatus": "COMPLETED"}))
        ratings = list(db.ratings.find({"isSubmitted": True}))

        sales_volume = defaultdict(int)
        rating_scores = defaultdict(list)
        dish_sentiment = defaultdict(list)

        # 1. Aggregate Sales Performance
        for order in completed_orders:
            for item in order.get("items", []):
                m_id = str(item.get("menuItemId"))
                sales_volume[m_id] += item.get("quantity", 1)

        # 2. Process Granular Dish Ratings & Comment Sentiment
        for r in ratings:
            comment = r.get('comment', '')
            s_score = get_sentiment(comment)

            # Update sentiment score in DB as a side effect (for Admin visibility)
            db.ratings.update_one({"_id": r["_id"]}, {"$set": {"sentimentScore": s_score}})

            granular = r.get('dishRatings', [])
            for ds in granular:
                m_id = str(ds.get('menuItemId'))
                rating_scores[m_id].append(ds.get('rating', 0))
                if s_score != 0:
                    dish_sentiment[m_id].append(s_score)

        # 3. Hybrid Scoring Logic (Weighting Volume + Satisfaction + Tone)
        scored_dishes = []
        for item in all_food_items:
            # Handle different ID formats (Node.js _id vs simple id string)
            m_id = str(item.get("_id") or item.get("id"))
            
            # Metric A: Popularity (Sales) - 50%
            volume = sales_volume.get(m_id, 0)

            # Metric B: Satisfaction (Stars) - 30%
            avg_r = sum(rating_scores[m_id]) / len(rating_scores[m_id]) if m_id in rating_scores else 0

            # Metric C: Tone (Sentiment) - 20%
            avg_s = sum(dish_sentiment[m_id]) / len(dish_sentiment[m_id]) if m_id in dish_sentiment else 0
            
            # Scale sentiment (-1 to 1) to match 0-5 stars range for fair weighting
            sentiment_bonus = avg_s * 5 

            # Formula: (Sales * 0.5) + (Avg Rating * 0.3) + (Sentiment Bonus * 0.2)
            final_score = (0.5 * volume) + (0.3 * avg_r) + (0.2 * sentiment_bonus)

            scored_dishes.append({
                "id": m_id,
                "name": item["name"],
                "score": round(final_score, 2),
                "sales": volume
            })

        # 4. Sort and Build Discovery Mix
        scored_dishes.sort(key=lambda x: x["score"], reverse=True)

        # Get Top 3 based on Score
        final_ids = [d["id"] for d in scored_dishes[:3]]

        # Select 2 Discovery items (New or Low Sales < 15) that aren't in the Top 3
        discovery_pool = [d["id"] for d in scored_dishes if d["sales"] < 15 and d["id"] not in final_ids]
        
        if discovery_pool:
            random.shuffle(discovery_pool)
            final_ids.extend(discovery_pool[:2])

        top_pick = scored_dishes[0]['name'] if scored_dishes else 'N/A'
        print(f"TOP AI PICK: {top_pick} (Score: {scored_dishes[0]['score'] if scored_dishes else 0})")

        return jsonify({"recommendations": final_ids})

    except Exception as e:
        print(f"Error in Recommendation Engine: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "AI Service Online", "port": 8000})

if __name__ == '__main__':
    # Running on localhost:8000 as per user requirements
    app.run(host='0.0.0.0', port=8000, debug=True)
