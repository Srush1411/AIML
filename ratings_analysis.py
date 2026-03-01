import math
import random
from bson import ObjectId
from textblob import TextBlob
from pymongo import UpdateOne

def custom_rating_round(avg):
    """
    Custom rounding logic requested:
    - If decimal is <= 0.5 (e.g., 4.2, 4.4, 4.5), floor it down
    - If decimal is >= 0.6 (e.g., 4.6, 4.8), ceil it up
    """
    decimal_part = avg - math.floor(avg)
    if decimal_part <= 0.5:
        return float(math.floor(avg))
    else:
        return float(math.ceil(avg))

def calculate_recommendations(db, user_id=None):
    """
    Hybrid Recommendation Engine with Order Volume Tracking and Guest Support.
    """
    is_guest = not user_id or str(user_id).lower() in ['null', 'undefined', 'none', '']
    print(f"\n--- AI DISCOVERY ENGINE START (User: {'GUEST' if is_guest else user_id}) ---")
    
    menu_col = db['menuitems']
    order_col = db['orders']
    
    # 1. Fetch available items
    query = {
        "$and": [
            {
                "$or": [
                    {"isAvailable": True},
                    {"isAvailable": "true"}
                ]
            },
            {"category": {"$ne": "drinks"}}
        ]
    }
    
    all_items = list(menu_col.find(query))
    
    if not all_items:
        print(f"!!! No available menu items found in 'menuitems' collection !!!")
        return []

    # 2. GLOBAL ORDER VOLUME TRACKING
    # We find out exactly how many times every dish has been ordered across the restaurant
    global_order_counts = {}
    try:
        all_completed_orders = list(order_col.find({"orderStatus": "COMPLETED"}))
        for order in all_completed_orders:
            for item in order.get('items', []):
                m_id = str(item.get('menuItemId') or item.get('_id'))
                global_order_counts[m_id] = global_order_counts.get(m_id, 0) + 1
    except Exception as e:
        print(f"-> Global Order Tracking Error: {e}")

    # 3. PERSONALIZATION LOGIC (Logged-in users only)
    user_history = []
    if not is_guest:
        try:
            user_orders = list(order_col.find({
                "userId": ObjectId(user_id), 
                "orderStatus": "COMPLETED" 
            }))
            
            for order in user_orders:
                for item in order.get('items', []):
                    m_id = str(item.get('menuItemId') or item.get('_id'))
                    if m_id:
                        user_history.append(m_id)
            print(f"-> Found {len(user_history)} past items in user history.")
        except Exception as e:
            print(f"-> User History Error: {e}")
    else:
        print("-> Guest User Detected. Relying on global order volume and ratings.")

    scored_dishes = []
    print(f"{'DISH NAME':<24} | {'RATING':<7} | {'REVIEWS':<7} | {'ORDERS':<7} | {'SCORE':<7}")
    print("-" * 70)

    for item in all_items:
        item_id = str(item['_id'])
        name = item.get('name', 'Unknown Dish')
        
        # Extract metadata
        avg_rating = item.get('averageRating', 0)
        review_count = item.get('totalReviews', 0)
        order_count = global_order_counts.get(item_id, 0)
        
        # --- NEW SCORING ALGORITHM ---
        # 1. Base Quality: Average Rating * 10 (Max 50 points)
        rating_points = avg_rating * 10
        
        # 2. Review Trust: Bonus for having lots of written reviews (Max 10 points)
        review_points = min(review_count * 2, 10)
        
        # 3. Order Popularity: Bonus based on the sheer number of times ordered (Max 25 points)
        popularity_points = min(order_count * 2, 25)
        
        # 4. Personalization: Boost items the logged-in user has ordered before
        personal_bonus = 15 if item_id in user_history else 0
        
        final_score = rating_points + review_points + popularity_points + personal_bonus
        
        print(f"{name[:23]:<24} | {avg_rating:<7.1f} | {review_count:<7} | {order_count:<7} | {final_score:<7.1f}")
        
        scored_dishes.append({
            "id": item_id,
            "name": name,
            "score": final_score,
            "reviews": review_count,
            "orders": order_count
        })

    # Sort by AI Score descending
    scored_dishes.sort(key=lambda x: x["score"], reverse=True)
    
    # --- BALANCING LOGIC: EXPLOITATION VS EXPLORATION ---
    
    # Step 1: Exploitation (Get the top 2 absolute best performing dishes)
    top_performers = scored_dishes[:2]
    top_ids = [d["id"] for d in top_performers]

    # Step 2: Exploration (Create a Discovery Pool)
    # Target items with low reviews OR low orders to give them exposure
    discovery_pool = [d for d in scored_dishes if d["id"] not in top_ids and (d["reviews"] < 5 or d["orders"] < 5)]
    
    # Fallback: If everything has high orders/reviews, just use any remaining items
    if not discovery_pool:
        discovery_pool = [d for d in scored_dishes if d["id"] not in top_ids]

    # Step 3: Randomly pick 2 dishes from the discovery pool
    random.shuffle(discovery_pool)
    discovery_picks = discovery_pool[:2]

    # Step 4: Combine them
    final_picks = top_performers + discovery_picks
    
    # Step 5: Shuffle the final list
    random.shuffle(final_picks)

    print("-" * 70)
    print(f"TOP PERFORMERS (Math): {[d['name'] for d in top_performers]}")
    print(f"DISCOVERY PICKS (Random): {[d['name'] for d in discovery_picks]}")
    print(f"FINAL SHUFFLED DISPLAY: {[d['name'] for d in final_picks]}")
    print("--- AI DISCOVERY ENGINE END ---\n")
    
    return [d["id"] for d in final_picks]

def sync_dish_rating(db, dish_id):
    """
    Syncs ratings from 'ratings' collection to 'menuitems' collection for a specific dish.
    """
    print(f"\n--- SYNCING RATING: {dish_id} ---")
    try:
        d_id = ObjectId(dish_id) if isinstance(dish_id, str) else dish_id
        
        rating_col = db['ratings']
        menu_col = db['menuitems']

        # 1. Fetch all submitted ratings for this specific dish
        cursor = rating_col.find({
            "dishRatings.menuItemId": d_id,
            "isSubmitted": True
        })
        
        feedbacks = list(cursor)
        
        if not feedbacks:
            menu_col.update_one(
                {"_id": d_id},
                {"$set": {"averageRating": 0, "totalReviews": 0, "sentimentScore": 0}}
            )
            return 0

        scores = []
        sentiments = []

        for f in feedbacks:
            for dr in f.get('dishRatings', []):
                if str(dr.get('menuItemId')) == str(d_id):
                    scores.append(dr.get('rating', 0))
            
            comment = f.get('comment', '')
            if comment:
                blob = TextBlob(comment)
                sentiments.append(blob.sentiment.polarity)

        if not scores:
            return 0

        # 2. Compute Averages with custom Floor/Ceil logic
        raw_avg_rating = sum(scores) / len(scores)
        final_rating = custom_rating_round(raw_avg_rating)
        
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0

        # 3. Persist to MenuItem
        menu_col.update_one(
            {"_id": d_id},
            {
                "$set": {
                    "averageRating": final_rating,
                    "totalReviews": len(scores),
                    "sentimentScore": round(avg_sentiment, 2)
                }
            }
        )
        
        print(f"-> Success: {final_rating} stars updated based on {len(scores)} reviews (Raw Math: {raw_avg_rating:.2f}).")
        return final_rating

    except Exception as e:
        print(f"!!! Sync Failed: {e}")
        return 0

def bulk_sync_all(db):
    """
    Highly Optimized Bulk Sync for MongoDB Free Tier (M0).
    Reduces hundreds of individual queries to just 1 Read and 2 Writes.
    """
    print("\n--- INITIATING OPTIMIZED GLOBAL RATING SYNC ---")
    try:
        rating_col = db['ratings']
        menu_col = db['menuitems']

        # 1. Fetch ALL submitted ratings
        all_feedbacks = list(rating_col.find({"isSubmitted": True}))
        print(f"-> Fetched {len(all_feedbacks)} total reviews from database.")

        # 2. Process math and NLP strictly in Python memory
        dish_stats = {}
        for f in all_feedbacks:
            comment = f.get('comment', '')
            sentiment = 0
            if comment:
                blob = TextBlob(comment)
                sentiment = blob.sentiment.polarity
            
            for dr in f.get('dishRatings', []):
                m_id = str(dr.get('menuItemId'))
                if m_id not in dish_stats:
                    dish_stats[m_id] = {'scores': [], 'sentiments': []}
                
                dish_stats[m_id]['scores'].append(dr.get('rating', 0))
                if comment:
                    dish_stats[m_id]['sentiments'].append(sentiment)

        # 3. Prepare Bulk Write Operations
        bulk_ops = []
        for m_id, stats in dish_stats.items():
            scores = stats['scores']
            sentiments = stats['sentiments']
            
            if not scores: continue

            raw_avg = sum(scores) / len(scores)
            final_rating = custom_rating_round(raw_avg)
            avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0

            bulk_ops.append(
                UpdateOne(
                    {"_id": ObjectId(m_id)},
                    {"$set": {
                        "averageRating": final_rating,
                        "totalReviews": len(scores),
                        "sentimentScore": round(avg_sentiment, 2)
                    }}
                )
            )

        # 4. Execute DB Updates efficiently
        menu_col.update_many({}, {"$set": {"averageRating": 0, "totalReviews": 0, "sentimentScore": 0}})
        
        if bulk_ops:
            menu_col.bulk_write(bulk_ops)

        print(f"--- GLOBAL SYNC COMPLETE: {len(bulk_ops)} dishes updated safely --- \n")
        return len(bulk_ops)

    except Exception as e:
        print(f"!!! Optimized Bulk Sync Failed: {e}")
        return 0