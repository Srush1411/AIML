import random
from collections import defaultdict
from textblob import TextBlob
from bson.objectid import ObjectId
import math
from bson.objectid import ObjectId

def calculate_average_rating(ratings, dish_id):
    """
    Calculates the average rating for a specific dish using granular data.
    """
    total = 0
    count = 0
    for r in ratings:
        dish_scores = r.get('dishRatings', [])
        found_granular = False
        for ds in dish_scores:
            if str(ds.get('menuItemId')) == str(dish_id):
                total += ds.get('rating', 0)
                count += 1
                found_granular = True
                break
        
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

        if "best" in text_lower or "amazing" in text_lower or "legendary" in text_lower:
            score += 0.2
            
        if "cold" in text_lower or "late" in text_lower or "salty" in text_lower:
            score -= 0.3
            
        return max(-1.0, min(1.0, score)) 
    except Exception as e:
        print(f"Sentiment Analysis Error: {e}")
        return 0

def calculate_recommendations(db, user_id=None):
    """
    Advanced Discovery Engine with Personalization & NLP Sentiment weighting.
    Formula: (Sales * 0.5) + (Avg Rating * 0.3) + (Sentiment * 0.2) + Personal Bonus
    """
    print(f"\n--- AI DISCOVERY ENGINE START (User: {user_id if user_id else 'GUEST'}) ---")

    all_food_items = list(db.menuitems.find({"isAvailable": True, "category": {"$ne": "drinks"}}))
    completed_orders = list(db.orders.find({"orderStatus": "COMPLETED"}))
    ratings = list(db.ratings.find({"isSubmitted": True}))

    sales_volume = defaultdict(int)
    rating_scores = defaultdict(list)
    dish_sentiment = defaultdict(list)

    # --- NEW: PERSONALIZATION DATA GATHERING ---
    user_ordered_items = set()
    user_favorite_categories = set()

    if user_id:
        try:
            # Find all past orders for this specific user
            user_orders = list(db.orders.find({"userId": ObjectId(user_id), "orderStatus": "COMPLETED"}))
            # Fallback if Node saves userId as string instead of ObjectId
            if not user_orders:
                user_orders = list(db.orders.find({"userId": str(user_id), "orderStatus": "COMPLETED"}))
                
            for order in user_orders:
                for item in order.get("items", []):
                    m_id = str(item.get("menuItemId"))
                    user_ordered_items.add(m_id)
            
            # Find categories of items the user has ordered
            for item in all_food_items:
                if str(item["_id"]) in user_ordered_items:
                    user_favorite_categories.add(item.get("category"))
        except Exception as e:
            print(f"Personalization Error (safe to ignore): {e}")

    # 1. Process Global Sales Volume
    for order in completed_orders:
        for item in order.get("items", []):
            m_id = str(item.get("menuItemId"))
            sales_volume[m_id] += item.get("quantity", 1)

    # 2. Process Granular Dish Ratings & Comment Sentiment
    for r in ratings:
        comment = r.get('comment', '')
        score = get_sentiment(comment)

        if "_id" in r:
            db.ratings.update_one({"_id": r["_id"]}, {"$set": {"sentimentScore": score}})

        granular = r.get('dishRatings', [])
        for ds in granular:
            m_id = str(ds.get('menuItemId'))
            rating_scores[m_id].append(ds.get('rating', 0))
            if score != 0:
                dish_sentiment[m_id].append(score)

    # 3. Hybrid Scoring Logic with Personalization
    scored_dishes = []
    for item in all_food_items:
        m_id = str(item["_id"])
        
        volume = sales_volume.get(m_id, 0)
        avg_r = sum(rating_scores[m_id]) / len(rating_scores[m_id]) if m_id in rating_scores and len(rating_scores[m_id]) > 0 else 0
        avg_s = sum(dish_sentiment[m_id]) / len(dish_sentiment[m_id]) if m_id in dish_sentiment and len(dish_sentiment[m_id]) > 0 else 0
        sentiment_bonus = avg_s * 5 
        
        # --- NEW: APPLY PERSONALIZATION BONUS ---
        personal_bonus = 0
        if user_id:
            if m_id in user_ordered_items:
                # Big boost: They have ordered this specific dish before
                personal_bonus += 5.0 
            elif item.get("category") in user_favorite_categories:
                # Small boost: They like this category (e.g., they buy a lot of "Desserts")
                personal_bonus += 2.0 

        # Formula: 50% Volume, 30% Stars, 20% NLP + User Bias
        final_score = (0.5 * volume) + (0.3 * avg_r) + (0.2 * sentiment_bonus) + personal_bonus

        scored_dishes.append({
            "id": m_id,
            "name": item.get("name", "Unknown"),
            "score": round(final_score, 2),
            "sales": volume
        })

    # 4. Final Mix Construction
    scored_dishes.sort(key=lambda x: x["score"], reverse=True)

    final_ids = [d["id"] for d in scored_dishes[:3]]

    discovery_pool = [d["id"] for d in scored_dishes if d["sales"] < 15 and d["id"] not in final_ids]
    
    if discovery_pool:
        random.shuffle(discovery_pool)
        final_ids.extend(discovery_pool[:2])

    return final_ids


def sync_dish_rating(db, dish_id):
    """
    NEW: Calculates average from 'ratings' and updates 'menuitems'
    Added at the bottom of the file as requested.
    """
    try:
        # Ensure dish_id is an ObjectId
        d_id = ObjectId(dish_id) if isinstance(dish_id, str) else dish_id

        # 1. Fetch all submitted ratings containing this dish
        ratings_cursor = db.ratings.find({
            "dishRatings.menuItemId": d_id,
            "isSubmitted": True
        })
        
        all_ratings = list(ratings_cursor)
        if not all_ratings:
            return 0

        # 2. Extract specific scores for this dish
        scores = []
        for r in all_ratings:
            for dr in r.get('dishRatings', []):
                if str(dr.get('menuItemId')) == str(d_id):
                    scores.append(dr.get('rating', 0))

        if not scores:
            return 0

        # 3. Calculate Ceiling Average (e.g., 4.1 becomes 5)
        avg = sum(scores) / len(scores)
        ceiling_avg = math.ceil(avg)

        # 4. Update the MenuItems collection so User 2 can see it
        db.menuitems.update_one(
            {"_id": d_id},
            {"$set": { "averageRating": ceiling_avg }}
        )
        
        print(f"Updated Dish {dish_id} to Average Rating: {ceiling_avg}")
        return ceiling_avg
    except Exception as e:
        print(f"Error in sync_dish_rating: {e}")
        return None