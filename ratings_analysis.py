
import os
import random
from collections import defaultdict
from textblob import TextBlob
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/Killa_db")
DB_NAME = os.getenv("DATABASE_NAME", "Killa_db")

def get_db():
    """Connects to the MongoDB instance."""
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]

def get_sentiment(text):
    """
    NLP Logic: Analyzes polarity from -1.0 (bad) to 1.0 (good).
    Used for offline data cleaning and batch processing.
    """
    if not text or len(text.strip()) < 3:
        return 0
    try:
        analysis = TextBlob(text)
        return analysis.sentiment.polarity
    except:
        return 0

def run_batch_sentiment_update():
    """
    Utility Function:
    Iterates through all submitted ratings and updates their sentimentScore in the DB.
    Useful for data maintenance.
    """
    db = get_db()
    ratings = list(db.ratings.find({"isSubmitted": True}))
    print(f"--- Starting Batch Sentiment Update for {len(ratings)} reviews ---")
    
    updated_count = 0
    for r in ratings:
        comment = r.get('comment', '')
        score = get_sentiment(comment)
        db.ratings.update_one(
            {"_id": r["_id"]},
            {"$set": {"sentimentScore": score}}
        )
        updated_count += 1
    
    print(f"--- Successfully updated {updated_count} records ---")

def calculate_recommendations_offline():
    """
    Standalone version of the recommendation engine.
    This can be used for generating reports or debugging the scoring logic
    without needing the Flask server to be active.
    """
    db = get_db()
    print("\n--- OFFLINE DISCOVERY ENGINE (NLP ENABLED) START ---")

    all_food_items = list(db.menuitems.find({"isAvailable": True, "category": {"$ne": "drinks"}}))
    completed_orders = list(db.orders.find({"orderStatus": "COMPLETED"}))
    ratings = list(db.ratings.find({"isSubmitted": True}))

    sales_volume = defaultdict(int)
    rating_scores = defaultdict(list)
    dish_sentiment = defaultdict(list)

    # 1. Process Sales
    for order in completed_orders:
        for item in order.get("items", []):
            m_id = str(item.get("menuItemId"))
            sales_volume[m_id] += item.get("quantity", 1)

    # 2. Process Granular Ratings & NLP Sentiment
    for r in ratings:
        comment = r.get('comment', '')
        score = get_sentiment(comment)
        
        granular = r.get('dishRatings', [])
        for ds in granular:
            m_id = str(ds.get('menuItemId'))
            rating_scores[m_id].append(ds.get('rating', 0))
            if score != 0:
                dish_sentiment[m_id].append(score)

    # 3. Hybrid Scoring Logic (50% Volume, 30% Stars, 20% Sentiment)
    scored_dishes = []
    for item in all_food_items:
        m_id = str(item.get("_id") or item.get("id"))
        volume = sales_volume.get(m_id, 0)
        
        avg_r = sum(rating_scores[m_id]) / len(rating_scores[m_id]) if m_id in rating_scores else 0
        avg_s = sum(dish_sentiment[m_id]) / len(dish_sentiment[m_id]) if m_id in dish_sentiment else 0
        
        # Scale sentiment (-1 to 1) to match 0-5 stars
        sentiment_bonus = avg_s * 5
        
        final_score = (0.5 * volume) + (0.3 * avg_r) + (0.2 * sentiment_bonus)

        scored_dishes.append({
            "id": m_id,
            "name": item["name"],
            "score": round(final_score, 2),
            "sales": volume
        })

    # 4. Sort and Build Discovery Mix
    scored_dishes.sort(key=lambda x: x["score"], reverse=True)
    
    # Top 3
    final_ids = [d["id"] for d in scored_dishes[:3]]
    
    # Discovery items (New or Low Sales)
    discovery_pool = [d["id"] for d in scored_dishes if d["sales"] < 15 and d["id"] not in final_ids]
    if discovery_pool:
        random.shuffle(discovery_pool)
        final_ids.extend(discovery_pool[:2])

    print("RANKING LOG (Top 5):")
    for d in scored_dishes[:5]:
        print(f"- {d['name']}: {d['score']}")
        
    return final_ids

if __name__ == "__main__":
    # If run directly, perform a test recommendation and batch update
    run_batch_sentiment_update()
    recommendations = calculate_recommendations_offline()
    print(f"\nRecommended IDs: {recommendations}")