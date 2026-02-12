from flask import Flask, request, jsonify
from pymongo import MongoClient
from ratings_analysis import calculate_average_rating, calculate_recommendations

app = Flask(__name__)

client = MongoClient("mongodb://localhost:27017")
db = client['restaurant']


@app.route('/aiml/test', methods=['GET'])
def test_aiml():
    return jsonify({
        "status": "AIML is running",
        "message": "Flask server working"
    })


@app.route('/average-rating', methods=['POST'])
def average_rating():
    dish_id = request.json['dishId']

    ratings = list(db.ratings.find())
    avg = calculate_average_rating(ratings, dish_id)

    return jsonify({
        "dishId": dish_id,
        "averageRating": avg
    })


@app.route('/aiml/recommend', methods=['GET'])
def recommend():

    recommendations = calculate_recommendations(db)

    return jsonify({
        "recommendations": recommendations
    })


if __name__ == '__main__':
    app.run(port=8000)
