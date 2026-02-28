import os
from flask import Flask, request, jsonify
from pymongo import MongoClient

# IMPORT THE EXTERNAL LOGIC FROM ratings_analysis.py
from ratings_analysis import calculate_recommendations

# Initialize Flask App (Main Server)
app = Flask(__name__)

# Database Connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DATABASE_NAME", "Killa_db")
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

@app.route('/aiml/recommend', methods=['POST'])
def recommend():
    """
    API Endpoint exposed to the Node.js backend to fetch AI recommendations.
    Communicates with ratings_analysis to process the math and NLP.
    """
    try:
        data = request.get_json() or {}
        user_id = data.get('userId')
        
        # Calculate recommendations using the imported ratings_analysis logic
        recommended_ids = calculate_recommendations(db)
        
        return jsonify({
            "success": True,
            "recommendations": recommended_ids
        }), 200
        
    except Exception as e:
        print(f"Recommendation Error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/', methods=['GET'])
def health_check():
    """
    Simple health check route to verify the AI server is running.
    """
    return jsonify({
        "status": "Killa AIML Engine is active on port 8000",
        "engine": "Communicating with ratings_analysis module successfully"
    }), 200

if __name__ == '__main__':
    # Running on 0.0.0.0 allows connections from other services/containers 
    # Port is explicitly set to 8000
    app.run(host='0.0.0.0', port=8000, debug=True)