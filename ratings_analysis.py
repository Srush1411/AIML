import random
from collections import defaultdict
from textblob import TextBlob

def calculate_average_rating(ratings, dish_id):
    """
    Calculates the average rating for a specific dish using granular data.
    """
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
        
        # 2. Fallback to general order rating if granular is missing
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
    """
    if not text or len(text.strip()) < 3:
        return 0

    try:
        analysis = TextBlob(text)
        score = analysis.sentiment.polarity
        text_lower = text.lower()

        # Keyword Boost Logic
        if "best" in text_lower or "amazing" in text_lower or "legendary" in text_lower:
            score += 0.2
            
        if "cold" in text_lower or "late" in text_lower or "salty" in text_lower:
            score -= 0.3
            
        return max(-1.0, min(1.0, score)) # Clamp between -1 and 1
    except Exception as e:
        print(f"Sentiment Analysis Error: {e}")
        return 0

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

    # 1. Process Sales Volume
    for order in completed_orders:
        for item in order.get("items", []):
            m_id = str(item.get("menuItemId"))
            sales_volume[m_id] += item.get("quantity", 1)

    # 2. Process Granular Dish Ratings & Comment Sentiment
    for r in ratings:
        comment = r.get('comment', '')
        score = get_sentiment(comment)

        # Log sentiment for the admin record in Mongo via a side-effect/update
        if "_id" in r:
            db.ratings.update_one({"_id": r["_id"]}, {"$set": {"sentimentScore": score}})

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
        avg_r = sum(rating_scores[m_id]) / len(rating_scores[m_id]) if m_id in rating_scores and len(rating_scores[m_id]) > 0 else 0

        # NLP Sentiment weighting
        avg_s = sum(dish_sentiment[m_id]) / len(dish_sentiment[m_id]) if m_id in dish_sentiment and len(dish_sentiment[m_id]) > 0 else 0
        
        # Scale sentiment (-1 to 1) to match 0-5 stars
        sentiment_bonus = avg_s * 5 
        
        # Formula: 50% Volume, 30% Granular Stars, 20% NLP Sentiment
        final_score = (0.5 * volume) + (0.3 * avg_r) + (0.2 * sentiment_bonus)

        scored_dishes.append({
            "id": m_id,
            "name": item.get("name", "Unknown"),
            "score": round(final_score, 2),
            "sales": volume
        })

    # 4. Final Mix Construction
    scored_dishes.sort(key=lambda x: x["score"], reverse=True)

    # Top 3 Picks
    final_ids = [d["id"] for d in scored_dishes[:3]]

    # 2 Random Discovery items (underperforming but good)
    discovery_pool = [d["id"] for d in scored_dishes if d["sales"] < 15 and d["id"] not in final_ids]
    
    if discovery_pool:
        random.shuffle(discovery_pool)
        final_ids.extend(discovery_pool[:2])

    top_pick_name = scored_dishes[0]['name'] if scored_dishes else 'N/A'
    top_pick_score = scored_dishes[0]['score'] if scored_dishes else 0
    print(f"TOP AI PICK: {top_pick_name} (Score: {top_pick_score})")
    
    return final_ids