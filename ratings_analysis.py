import random
from collections import defaultdict
from datetime import datetime

def calculate_average_rating(ratings, dish_id):
    """Calculates the average rating for a specific dish."""
    total = 0
    count = 0
    for r in ratings:
        if str(r.get('menuItemId')) == str(dish_id):
            total += r.get('rating', 0)
            count += 1
    return round(total / count, 1) if count > 0 else 0


def calculate_recommendations(db):
    """
    Advanced Recommendation Engine (Food Only):
    Filters out 'drinks' and focuses on Veg/Non-Veg.
    Mixes Top-Sellers (3 items) with Random New Arrivals (2 items) for discovery.
    """
    print("\n--- AI DISCOVERY ENGINE (FOOD ONLY) START ---")
    
    # 1. Fetch data from MongoDB
    # Exclude 'drinks' category from recommendations
    all_food_items = list(db.menuitems.find({
        "isAvailable": True,
        "category": {"$ne": "drinks"}
    }))
    
    completed_orders = list(db.orders.find({"orderStatus": "COMPLETED"}))
    ratings = list(db.ratings.find())

    # Data structures for scoring
    sales_volume = defaultdict(int)
    rating_scores = defaultdict(list)
    
    # 2. Process Sales Volume
    for order in completed_orders:
        for item in order.get("items", []):
            m_id = str(item["menuItemId"])
            sales_volume[m_id] += item.get("quantity", 1)

    # 3. Process Ratings
    for r in ratings:
        m_id = str(r.get("menuItemId"))
        rating_scores[m_id].append(r.get("rating", 0))

    # 4. Score Food Items
    scored_dishes = []
    for item in all_food_items:
        m_id = str(item["_id"])
        
        # Calculate Base Stats
        volume = sales_volume.get(m_id, 0)
        avg_r = sum(rating_scores[m_id]) / len(rating_scores[m_id]) if m_id in rating_scores else 0
        
        # Scoring Formula: 60% Volume, 40% Rating
        score = (0.6 * volume) + (0.4 * avg_r)
        
        scored_dishes.append({
            "id": m_id,
            "name": item["name"],
            "score": round(score, 1),
            "sales": volume,
            "createdAt": item.get("createdAt", datetime.min)
        })

    # Sort by performance (Top Sellers)
    scored_dishes.sort(key=lambda x: x["score"], reverse=True)

    # 5. Identify "Discovery Candidates" (Randomized Selection)
    # Get all food items with low sales count (< 15)
    discovery_pool = [d for d in scored_dishes if d["sales"] < 15]
    
    # 6. Construct Final Hybrid List (Mix: 3 Top Sellers + 2 Random Discovery)
    final_recommendation_ids = []
    
    # Take top 3 established performers
    for d in scored_dishes[:3]:
        final_recommendation_ids.append(d["id"])
        print(f" [ESTABLISHED FOOD] {d['name']} - Score: {d['score']}")

    # Randomized Discovery: Pick 2 random items from the discovery pool
    # Excluding those already in the top 3
    remaining_discovery_pool = [d for d in discovery_pool if d["id"] not in final_recommendation_ids]
    
    if remaining_discovery_pool:
        # Shuffle the pool for randomness
        random.shuffle(remaining_discovery_pool)
        
        added_discovery = 0
        for n in remaining_discovery_pool:
            final_recommendation_ids.append(n["id"])
            print(f" [RANDOM DISCOVERY] {n['name']} - Promoted")
            added_discovery += 1
            if added_discovery >= 2:
                break

    # Final Guard: Fill up to 5 if the list is still short
    if len(final_recommendation_ids) < 5:
        for d in scored_dishes:
            if d["id"] not in final_recommendation_ids:
                final_recommendation_ids.append(d["id"])
            if len(final_recommendation_ids) >= 5:
                break

    print(f"FINAL FOOD-ONLY OUTPUT: {final_recommendation_ids}")
    print("--- AI DISCOVERY ENGINE END ---\n")

    return final_recommendation_ids