import random
from collections import defaultdict
from datetime import datetime
from textblob import TextBlob  # Required: pip install textblob

def calculate_average_rating(ratings, dish_id):
    """Calculates the average rating for a specific dish using granular data."""
    total = 0
    count = 0
    for r in ratings:
        # 1. Prioritize granular dish ratings
        dish_scores = r.get('dishRatings', [])
        found_granular = False
        
        for ds in dish_scores:
            if str(ds.get('menuItemId')) == str(dish_id):
                total += ds.get('rating', 0)
                count += 1
                found_granular = True
                break
        
        # 2. Fallback to general order rating if granular is missing (backward compatibility)
        if not found_granular:
            items = r.get('items', [])
            for item in items:
                if str(item.get('menuItemId')) == str(dish_id):
                    total += r.get('rating', 0)
                    count += 1
                    break
                    
    return round(total / count, 1) if count > 0 else 0

def get_sentiment(text):
    """
    NLP Logic: Analyzes polarity from -1.0 (very negative) to 1.0 (very positive).
    We use this to adjust dish ranking scores beyond just simple star ratings.
    """
    if not text or len(text.strip()) < 3:
        return 0
    
    try:
        analysis = TextBlob(text)
        score = analysis.sentiment.polarity
        
        # Keyword Boost Logic: Manual correction for common restaurant terms
        text_lower = text.lower()
        if "best" in text_lower or "amazing" in text_lower or "legendary" in text_lower:
            score += 0.2
        if "cold" in text_lower or "late" in text_lower or "salty" in text_lower:
            score -= 0.3
            
        return max(-1.0, min(1.0, score)) # Clamp between -1 and 1
    except:
        return 0

def calculate_recommendations(db):
    """
    AI Discovery Engine v2 (Sentiment Aware).
    New Scoring Formula: (Sales * 0.4) + (Granular Avg * 0.4) + (Sentiment Score * 0.2)
    """
    print("\n--- AI SENTIMENT ENGINE START ---")

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
        # Calculate sentiment for the overall review
        s_score = get_sentiment(comment)
        
        # Save sentiment back to DB for Admin viewing (side-effect)
        db.ratings.update_one({"_id": r["_id"]}, {"$set": {"sentimentScore": s_score}})
        
        granular = r.get('dishRatings', [])
        for ds in granular:
            m_id = str(ds.get('menuItemId'))
            rating_scores[m_id].append(ds.get('rating', 0))
            if s_score != 0:
                dish_sentiment[m_id].append(s_score)

    # 3. Apply Hybrid Scoring (Weighting Volume + Satisfaction + Tone)
    scored_dishes = []
    for item in all_food_items:
        m_id = str(item["_id"])
        
        # Metric A: Popularity (Sales)
        volume = sales_volume.get(m_id, 0)
        
        # Metric B: Satisfaction (Stars)
        avg_r = sum(rating_scores[m_id]) / len(rating_scores[m_id]) if m_id in rating_scores else 0
        
        # Metric C: Tone (Sentiment)
        avg_s = sum(dish_sentiment[m_id]) / len(dish_sentiment[m_id]) if m_id in dish_sentiment else 0
        sentiment_bonus = avg_s * 5 # Scale -1 to 1 into a star-comparable weight
        
        # Formula: 40% Sales, 40% Stars, 20% AI Tone
        final_score = (0.4 * volume) + (0.4 * avg_r) + (0.2 * sentiment_bonus)

        scored_dishes.append({
            "id": m_id,
            "name": item["name"],
            "score": round(final_score, 2),
            "sales": volume
        })

    # 4. Sort and Build Discovery Mix
    scored_dishes.sort(key=lambda x: x["score"], reverse=True)
    
    # Top 3 based on Score
    final_ids = [d["id"] for d in scored_dishes[:3]]
    
    # Select 2 Discovery items (New or Low Sales)
    discovery_pool = [d["id"] for d in scored_dishes if d["sales"] < 15 and d["id"] not in final_ids]
    if discovery_pool:
        random.shuffle(discovery_pool)
        final_ids.extend(discovery_pool[:2])

    print(f"TOP AI PICK: {scored_dishes[0]['name'] if scored_dishes else 'N/A'} (Score: {scored_dishes[0]['score'] if scored_dishes else 0})")
    return final_ids