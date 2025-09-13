import json
from shapely.geometry import Point, Polygon
import time
from dotenv import load_dotenv
import os
from twilio.rest import Client

# --- Geo-Fence Management ---

def load_geofences(file_path="geofences.json"):
    """
    Loads geo-fence definitions from an external JSON file.
    This allows for dynamic updates without changing code.
    """
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"WARNING: Geo-fence file not found at {file_path}. No zones will be loaded.")
        return []
    except json.JSONDecodeError:
        print(f"WARNING: Could not decode {file_path}. Is it valid JSON?")
        return []

# Load the zones when the engine starts up
GEO_ZONES = load_geofences()

def check_location_status(latitude, longitude):
    """
    Checks a GPS coordinate against all loaded geo-zones and returns the status.
    Returns the 'type' of the zone the tourist is in (e.g., 'safe_zone').
    """
    tourist_location = Point(longitude, latitude)
    
    for zone in GEO_ZONES:
        zone_polygon = Polygon(zone['coordinates'])
        if zone_polygon.contains(tourist_location):
            # Return the type and name of the zone they are in
            return zone['type'], zone['name']
            
    # If not in any defined zone, they are in an unmonitored area
    return "unmonitored", None


# --- AI Anomaly Detection (Unchanged) ---
STATIONARY_THRESHOLD_SECONDS = 10 # 30 minutes

def check_stationary_anomaly(last_location_data):
    """
    Checks if a tourist has been stationary for too long.
    """
    if not last_location_data:
        return False, "No previous location data."

    time_since_last_update = time.time() - last_location_data.get('timestamp', 0)
    
    if time_since_last_update > STATIONARY_THRESHOLD_SECONDS:
        minutes = int(time_since_last_update / 60)
        return True, f"Tourist has been stationary for over {minutes} minutes."
    
    return False, "Tourist is moving normally."


# --- Emergency Alerting Function (Unchanged) ---
def send_emergency_alert(tourist_name, tourist_id, emergency_contact, location, reason):
    """
    Simulates sending an emergency SMS alert to the tourist's close one.
    """
    latitude, longitude = location
    maps_link = f"https://www.google.com/maps?q={latitude},{longitude}"
    
    alert_message = (
        f"\n"
        f"************************************************************\n"
        f"** EMERGENCY ALERT NOTIFICATION                            **\n"
        f"************************************************************\n"
        f"** SIMULATING SMS to: {emergency_contact} \n"
        f"**----------------------------------------------------------\n"
        f"** MESSAGE: \n"
        f"** Urgent safety alert for {tourist_name} (ID: {tourist_id[:20]}...).\n"
        f"** REASON: {reason}\n"
        f"** Last known location: {maps_link}\n"
        f"** Please attempt to contact them. Authorities are being notified.\n"
        f"************************************************************\n"
    )
    
    print(alert_message)

def send_real_sms_alert(tourist_name, location, reason):
    """Sends an emergency SMS using Twilio to a real phone number."""
    load_dotenv()
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    twilio_number = os.getenv('TWILIO_PHONE_NUMBER')
    recipient_number = os.getenv('EMERGENCY_CONTACT_PHONE_NUMBER')

    if not all([account_sid, auth_token, twilio_number, recipient_number]):
        print("   - ⚠️  WARNING: Twilio credentials not fully configured in .env file. Skipping real SMS.")
        return

    try:
        client = Client(account_sid, auth_token)
        maps_link = f"https://www.google.com/maps?q={location[0]},{location[1]}"
        message_body = (
            f"Urgent Safety Alert for {tourist_name}.\n"
            f"Reason: {reason}\n"
            f"Last Location: {maps_link}"
        )
        
        message = client.messages.create(
            from_=twilio_number,
            body=message_body,
            to=recipient_number
        )
        print(f"   - ✅ SUCCESS: Real SMS alert sent to {recipient_number} (SID: {message.sid})")
    except Exception as e:
        print(f"   - ❌ ERROR: Failed to send SMS via Twilio: {e}")

