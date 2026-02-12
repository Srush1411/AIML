from collections import defaultdict

def calculate_average_rating(ratings, dish_id):
    total = 0
    count = 0

    for r in ratings:
        if str(r['menuItemId']) == str(dish_id):
            total += r['rating']
            count += 1

    if count == 0:
        return 0

    return round(total / count, 1)


# 🔥 ADD THIS NEW FUNCTION BELOW

def calculate_recommendations(db):

    orders = db.orders.find()
    ratings = db.ratings.find()

    order_score = defaultdict(int)
    rating_data = defaultdict(list)

    # Count order frequency
    for order in orders:
        for item in order.get("items", []):
            menu_id = str(item["menuItemId"])
            order_score[menu_id] += item["quantity"]

    # Collect ratings
    for rating in ratings:
        order = db.orders.find_one({"_id": rating["orderId"]})
        if order:
            for item in order.get("items", []):
                menu_id = str(item["menuItemId"])
                rating_data[menu_id].append(rating["rating"])

    final_score = {}

    for menu_id, count in order_score.items():
        avg_rating = 0
        if menu_id in rating_data:
            avg_rating = sum(rating_data[menu_id]) / len(rating_data[menu_id])

        final_score[menu_id] = (0.7 * count) + (0.3 * avg_rating)

    sorted_items = sorted(
        final_score.items(),
        key=lambda x: x[1],
        reverse=True
    )

    top_5 = [item[0] for item in sorted_items[:5]]

    return top_5
