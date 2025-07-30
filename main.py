from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import uuid
from datetime import datetime
import logging
import requests
import os

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)

DATA_FILE = 'user_data.json'
AI_RESPONSE_FILE = 'ai_recommendations.json'
N8N_REMINDER_WEBHOOK = 'https://h12user.app.n8n.cloud/webhook/webhook-test/medical-analysis'

def initialize_data_files():
    for file in [DATA_FILE, AI_RESPONSE_FILE]:
        if not os.path.exists(file):
            with open(file, 'w') as f:
                json.dump([] if file == DATA_FILE else {}, f)

def format_ai_response(raw):
    """Format AI response for frontend consumption"""
    try:
        # Handle different possible structures
        if isinstance(raw, list) and len(raw) > 0:
            raw = raw[-1]  # Get the latest response
        
        if not isinstance(raw, dict):
            return {}
            
        response = {
            "predicted_condition": raw.get("predicted_condition", "Analysis pending..."),
            "medication_alerts": raw.get("medication_alerts", []),
            "home_remedies": raw.get("home_remedies", []),
            "diet_plan": raw.get("diet_plan", []),
            "youtube_videos": raw.get("youtube_videos", [])
        }
        return response
    except Exception as e:
        logging.error(f"Error formatting AI response: {e}")
        return {}

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/health')
def health_check():
    return jsonify({"status": "Server is up!", "timestamp": datetime.now().isoformat()})

@app.route('/submit', methods=['POST'])
def save_and_trigger():
    try:
        new_user_data = request.get_json()
        
        # Add metadata
        new_user_data['user_id'] = str(uuid.uuid4())
        new_user_data['timestamp'] = datetime.now().isoformat()
        new_user_data['server_received_at'] = datetime.now().isoformat()
        
        # Ensure medications field exists and is properly formatted
        if 'medications' not in new_user_data:
            new_user_data['medications'] = []

        # Save to user data file
        try:
            with open(DATA_FILE, 'r') as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = []
                except json.JSONDecodeError:
                    data = []
        except FileNotFoundError:
            data = []

        data.append(new_user_data)
        
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)

        logging.info(f"User data saved with ID: {new_user_data['user_id']}")

        # Clear any previous AI response
        with open(AI_RESPONSE_FILE, 'w') as f:
            json.dump({}, f)

        # Trigger n8n webhook
        try:
            webhook_response = requests.post(
                N8N_REMINDER_WEBHOOK, 
                json=new_user_data, 
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            webhook_response.raise_for_status()
            logging.info("Successfully triggered n8n webhook")
            
            return jsonify({
                "success": True,
                "message": "Data saved and AI analysis triggered",
                "user_id": new_user_data['user_id']
            }), 200
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Webhook error: {e}")
            return jsonify({
                "success": True,
                "message": "Data saved but AI analysis failed to trigger",
                "error": str(e)
            }), 202

    except Exception as e:
        logging.exception("Failed to save data")
        return jsonify({
            "success": False,
            "error": "Failed to process submission",
            "details": str(e)
        }), 500

@app.route('/get-ai-response', methods=['GET'])
def get_ai_response():
    """Endpoint that matches what the frontend is calling"""
    try:
        # Try to read from the main AI response file
        with open(AI_RESPONSE_FILE, 'r') as f:
            ai_data = json.load(f)
        
        # Check if we have any meaningful data
        if not ai_data or (isinstance(ai_data, dict) and len(ai_data) == 0):
            return jsonify({}), 200
        
        # Format the response for the frontend
        formatted_response = format_ai_response(ai_data)
        
        # Return the formatted response
        return jsonify(formatted_response), 200
        
    except FileNotFoundError:
        logging.warning("AI response file not found")
        return jsonify({}), 200
    except json.JSONDecodeError:
        logging.error("Invalid JSON in AI response file")
        return jsonify({}), 200
    except Exception as e:
        logging.error(f"Error retrieving AI response: {e}")
        return jsonify({"error": "Could not load AI response"}), 500

@app.route('/get_recommendations', methods=['GET'])
def get_recommendations():
    """Legacy endpoint - redirects to new endpoint"""
    return get_ai_response()

# Webhook endpoint for n8n to save AI response
@app.route('/save-ai-response', methods=['POST'])
def save_ai_response():
    """Endpoint for n8n to save the AI analysis result"""
    try:
        ai_response = request.get_json()
        
        with open(AI_RESPONSE_FILE, 'w') as f:
            json.dump(ai_response, f, indent=4)
        
        logging.info("AI response saved successfully")
        return jsonify({"success": True, "message": "AI response saved"}), 200
        
    except Exception as e:
        logging.error(f"Failed to save AI response: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/debug/latest-user', methods=['GET'])
def get_latest_user():
    """Debug endpoint to see the latest user data"""
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        
        if data and len(data) > 0:
            return jsonify(data[-1]), 200
        else:
            return jsonify({"message": "No user data found"}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug/ai-response', methods=['GET'])
def debug_ai_response():
    """Debug endpoint to see the current AI response"""
    try:
        with open(AI_RESPONSE_FILE, 'r') as f:
            data = json.load(f)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    initialize_data_files()
    print("🏥 MediTrack+ AI Server Starting...")
    print("📁 Data files initialized")
    print("🌐 Server will be available at:")
    print("   - http://localhost:5000")
    print("   - http://127.0.0.1:5000")
    print("   - http://0.0.0.0:5000")
    
    # Try to get local IP
    import socket
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"   - http://{local_ip}:5000")
    except:
        pass
    
    app.run(debug=True, port=5000, host='0.0.0.0')
