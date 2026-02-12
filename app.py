from flask import Flask, request, jsonify
from pymongo import MongoClient
from ratings_analysis import calculate_average_rating, calculate_recommendations

app = Flask(__name__)

# Database Configuration
MONGO_URL = "mongodb://localhost:27017"
DATABASE_NAME = "Killa_db" 

client = MongoClient(MONGO_URL)
db = client[DATABASE_NAME]

@app.route('/aiml/test', methods=['GET'])
def test_aiml():
    return jsonify({
        "status": "AIML Service Active",
        "database": DATABASE_NAME
    })

@app.route('/average-rating', methods=['POST'])
def average_rating():
    try:
        data = request.get_json()
        dish_id = data.get('dishId')
        ratings = list(db.ratings.find())
        avg = calculate_average_rating(ratings, dish_id)
        return jsonify({"dishId": dish_id, "averageRating": avg})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/aiml/recommend', methods=['POST'])
def recommend():
    """
    Handles both logged-in and guest recommendation requests.
    Returns a mix of high-performers and new arrivals.
    """
    try:
        # Extract userId (used for logging or future personalization)
        data = request.get_json() or {}
        user_id = data.get('userId')
        
        # Calculate hybrid recommendations (Discovery Mode)
        recommendations = calculate_recommendations(db)
        
        return jsonify({
            "recommendations": recommendations,
            "mode": "Discovery",
            "personalized": user_id is not None
        })
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"recommendations": [], "error": "Analysis failed"}), 500

if __name__ == '__main__':
    app.run(port=8000, debug=True)