import random
from collections import defaultdict
from datetime import datetime
from textblob import TextBlob  # NEW: NLP library for Sentiment Analysis

def calculate_average_rating(ratings, dish_id):
    """Calculates the average rating for a specific dish using granular data."""
    total = 0
    count = 0
    for r in ratings:
        # Check granular dish ratings if they exist
        dish_scores = r.get('dishRatings', [])
        found_granular = False
        
        for ds in dish_scores:
            if str(ds.get('menuItemId')) == str(dish_id):
                total += ds.get('rating', 0)
                count += 1
                found_granular = True
                break
        
        # Fallback to general order rating if granular is missing
        if not found_granular:
            items = r.get('items', [])
            for item in items:
                if str(item.get('menuItemId')) == str(dish_id):
                    total += r.get('rating', 0)
                    count += 1
                    break
                    
    return round(total / count, 1) if count > 0 else 0

def get_sentiment(text):
    """NLP Logic: Analyzes polarity from -1.0 (bad) to 1.0 (good)."""
    if not text or len(text.strip()) < 3:
        return 0
    analysis = TextBlob(text)
    return analysis.sentiment.polarity

def calculate_recommendations(db):
    """
    Advanced Discovery Engine with NLP Sentiment weighting.
    Formula: (Sales * 0.5) + (Avg Rating * 0.3) + (Sentiment * 0.2)
    """
    print("\n--- AI DISCOVERY ENGINE (NLP ENABLED) START ---")

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
        
        # Log sentiment for the admin record in Mongo via a side-effect/update
        # (Usually done in a background job, here we just use it for ranking)
        
        granular = r.get('dishRatings', [])
        for ds in granular:
            m_id = str(ds.get('menuItemId'))
            rating_scores[m_id].append(ds.get('rating', 0))
            if score != 0:
                dish_sentiment[m_id].append(score)

    # 3. Hybrid Scoring Logic
    scored_dishes = []
    for item in all_food_items:
        m_id = str(item["_id"])
        volume = sales_volume.get(m_id, 0)
        
        # Granular Stars
        avg_r = sum(rating_scores[m_id]) / len(rating_scores[m_id]) if m_id in rating_scores else 0
        
        # NLP Sentiment weighting
        avg_s = sum(dish_sentiment[m_id]) / len(dish_sentiment[m_id]) if m_id in dish_sentiment else 0
        sentiment_bonus = avg_s * 5 # Scale sentiment (-1 to 1) to match 0-5 stars
        
        # Formula: 50% Volume, 30% Granular Stars, 20% NLP Sentiment
        final_score = (0.5 * volume) + (0.3 * avg_r) + (0.2 * sentiment_bonus)

        scored_dishes.append({
            "id": m_id,
            "name": item["name"],
            "score": round(final_score, 2),
            "sales": volume
        })

    # 4. Final Mix Construction
    scored_dishes.sort(key=lambda x: x["score"], reverse=True)
    
    final_ids = [d["id"] for d in scored_dishes[:3]] # Top 3
    discovery_pool = [d["id"] for d in scored_dishes if d["sales"] < 15 and d["id"] not in final_ids]
    
    if discovery_pool:
        random.shuffle(discovery_pool)
        final_ids.extend(discovery_pool[:2]) # Add 2 randoms

    print(f"RANKING LOG: {scored_dishes[:5]}")
    return final_ids