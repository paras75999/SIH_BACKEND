from flask import Flask, request, jsonify
import asyncio
import json
import time
# Import the core logic from your other files
from cred2 import issue_tourist_credential, anchor_vc, save_vc_to_file
from geofenc import check_location_status, send_emergency_alert, check_stationary_anomaly

app = Flask(__name__)

# --- In-Memory "Database" ---
# In a real app, this would be a proper database like PostgreSQL or MongoDB
TOURIST_DATABASE = {} # Stores { "touristId": {"name": "...", "emergencyContact": "..."} }
TOURIST_LOCATIONS = {} # Stores { "touristId": {"lat": ..., "lon": ..., "timestamp": ...} }


@app.route('/api/issueTouristCredential', methods=['POST'])
def issue_credential():
    """
    API endpoint to issue a new credential, anchor it, and store tourist info.
    """
    print("\nReceived request to issue a new Tourist Credential...")
    tourist_data = request.get_json()
    if not tourist_data:
        return jsonify({"error": "Invalid JSON data provided."}), 400

    try:
        # Use asyncio.run() to execute our async credential issuance function
        # from the synchronous context of this Flask endpoint.
        issued_vc_str = asyncio.run(issue_tourist_credential(tourist_data))
        
        # Now, anchor the credential synchronously
        tx_hash = anchor_vc(issued_vc_str)
        
        if not tx_hash:
            raise Exception("Failed to anchor the credential on the blockchain after issuance.")

        # Save the credential to a file for the Responder App to find.
        # This is a simple way to pass data between personas in our demo.
        save_vc_to_file(issued_vc_str, filename="latest_vc_for_responder.json")

        # Parse the VC to store emergency contact info in our "database"
        vc_json = json.loads(issued_vc_str)
        # The issuer DID is the unique ID for the tourist in our system
        tourist_id = vc_json.get('issuer') 
        tourist_info = vc_json.get('credentialSubject', {}).get('touristInfo', {})
        
        if tourist_id:
            TOURIST_DATABASE[tourist_id] = {
                "name": tourist_info.get('name'),
                "emergencyContact": tourist_info.get('emergencyContact')
            }
            # Initialize their location for the monitoring dashboard
            TOURIST_LOCATIONS[tourist_id] = {} 
            print(f"   - Stored emergency info for {tourist_info.get('name')}")

        # Send a success response back to the Streamlit app
        return jsonify({
            "status": "success",
            "message": "Credential issued and anchored successfully.",
            "transactionHash": tx_hash,
            "credential": vc_json # Send the full credential back
        }), 201

    except Exception as e:
        # If anything in the engine fails, send a detailed error back
        print(f"   ❌ An internal error occurred: {e}")
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500


@app.route('/api/update_location', methods=['POST'])
def update_location():
    """
    API endpoint to receive location updates and check against multiple geo-fences.
    """
    data = request.get_json()
    lat, lon, tourist_id = data.get('latitude'), data.get('longitude'), data.get('touristId')

    if not all([lat, lon, tourist_id]):
        return jsonify({"error": "Missing latitude, longitude, or touristId."}), 400

    # Store the latest location for AI anomaly detection
    TOURIST_LOCATIONS[tourist_id] = {"lat": lat, "lon": lon, "timestamp": time.time()}
    
    # --- UPDATED LOGIC ---
    # Use the new function to get the status based on multiple zones
    status, zone_name = check_location_status(lat, lon)
    tourist_info = TOURIST_DATABASE.get(tourist_id)

    if status == "restricted_zone":
        print(f"🚨 ALERT! Tourist {tourist_id[:20]}... has entered a RESTRICTED ZONE: {zone_name}")
        if tourist_info:
            send_emergency_alert(
                tourist_name=tourist_info['name'], tourist_id=tourist_id,
                emergency_contact=tourist_info['emergencyContact'], location=(lat, lon),
                reason=f"Tourist has entered a restricted area: {zone_name}"
            )
        return jsonify({"status": "alert", "message": f"Tourist entered restricted zone: {zone_name}"})

    # Check for AI anomaly (only if they are not in a restricted zone)
    is_anomaly, reason = check_stationary_anomaly(TOURIST_LOCATIONS.get(tourist_id))
    if is_anomaly:
        print(f"🚨 AI ALERT! {reason} for tourist {tourist_id[:20]}...")
        if tourist_info:
             send_emergency_alert(
                tourist_name=tourist_info['name'], tourist_id=tourist_id,
                emergency_contact=tourist_info['emergencyContact'], location=(lat, lon),
                reason=reason
            )
        return jsonify({"status": "alert", "message": reason})

    # If not in a restricted zone and no AI anomaly, report their current zone status
    message = f"Tourist is in '{zone_name}' ({status})." if zone_name else "Tourist is in an unmonitored area."
    print(f"INFO: Location update from {tourist_id[:20]}...: {status.upper()} at ({lat}, {lon})")
    return jsonify({"status": status, "message": message})


if __name__ == '__main__':
    print("Starting Flask backend server on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)

