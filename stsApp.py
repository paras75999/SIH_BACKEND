import streamlit as st
import json
import requests
import qrcode
from PIL import Image
from io import BytesIO
import time
import pandas as pd
import folium
from streamlit_folium import st_folium

# Import your local verification and monitoring engines
from verification_enginee import verify_vc_signature, verify_anchor
from geofenc import load_geofences

# --- Page Configuration ---
st.set_page_config(
    layout="wide",
    page_title="Smart Tourist Safety System",
    page_icon="🛡️"
)

# --- App State Management ---
# Using session_state to hold data across page reruns
if 'tourist_data' not in st.session_state:
    st.session_state.tourist_data = [] # Will store dicts of tourist info
if 'latest_vc_string' not in st.session_state:
    st.session_state.latest_vc_string = None
if 'latest_qr_image' not in st.session_state:
    st.session_state.latest_qr_image = None

# --- API Configuration ---
BACKEND_URL = "http://127.0.0.1:5000"


# --- Sidebar Navigation ---
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Citizen / Tourist", "First Responder", "Live Monitoring Dashboard"])
st.sidebar.markdown("---")


# ==============================================================================
# --- CITIZEN / TOURIST VIEW ---
# ==============================================================================
if page == "Citizen / Tourist":
    st.title("🛡️ Citizen & Tourist Digital Wallet")
    st.markdown("---")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.header("Issue a New Digital ID")
        st.caption("Enter your details as they appear on your official documents.")
        with st.form("tourist_form"):
            name = st.text_input("Full Name", "Priya Sharma")
            nationality = st.text_input("Nationality", "British")
            passport = st.text_input("Passport Number", "G987654321")
            contact = st.text_input("Emergency Contact", "+44 20 7946 0999")
            blood_type = st.selectbox("Blood Type", ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"])
            insurance = st.text_input("Insurance Policy ID", "INS-AETNA-5588-XYZ")
            
            submitted = st.form_submit_button("Get My Digital ID")

        if submitted:
            with st.spinner("Issuing your secure Digital ID... This may take a moment."):
                tourist_payload = {
                    "name": name, "nationality": nationality, "passportNumber": passport,
                    "emergencyContact": contact, "bloodType": blood_type, "insurancePolicyId": insurance
                }
                try:
                    # Make the API call to the Flask backend
                    response = requests.post(f"{BACKEND_URL}/api/issueTouristCredential", json=tourist_payload)
                    response.raise_for_status() # Raises an exception for bad status codes (4xx or 5xx)

                    response_data = response.json()
                    st.session_state.latest_vc_string = json.dumps(response_data.get('credential'))

                    # Generate QR Code from the VC string
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(st.session_state.latest_vc_string)
                    qr.make(fit=True)
                    img = qr.make_image(fill='black', back_color='white')
                    
                    # Save QR code to a BytesIO object to be downloadable
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    st.session_state.latest_qr_image = buf.getvalue()

                    # Add new tourist to our list for the monitoring demo
                    new_tourist_id = response_data.get('credential', {}).get('issuer')
                    if new_tourist_id:
                        # Avoid adding duplicate tourists
                        if not any(t['id'] == new_tourist_id for t in st.session_state.tourist_data):
                            st.session_state.tourist_data.append({
                                "id": new_tourist_id, "name": name, 
                                "lat": 28.4575, "lon": 77.0263 # Start location inside park
                            })
                    
                    st.success("Your Digital ID has been issued and anchored successfully!")

                except requests.exceptions.RequestException as e:
                    st.error(f"Failed to connect to the backend server. Is it running? Details: {e}")
                except Exception as e:
                    st.error(f"An error occurred. Check the backend server terminal for details. Error: {e}")

    with col2:
        st.header("Your Digital ID")
        if st.session_state.latest_vc_string:
            st.success("Here is your newly issued Digital ID. You can now download the QR code.")
            st.image(st.session_state.latest_qr_image, caption="Your Digital ID QR Code", width=300)

            st.download_button(
               label="Download QR Code",
               data=st.session_state.latest_qr_image,
               file_name="tourist_qr_code.png",
               mime="image/png"
            )
            with st.expander("View Raw Credential Data"):
                st.json(json.loads(st.session_state.latest_vc_string))
        else:
            st.info("Your new Digital ID and QR code will appear here once it is issued.")


# ==============================================================================
# --- FIRST RESPONDER VIEW ---
# ==============================================================================
elif page == "First Responder":
    st.title("👮‍♂️ First Responder Verification Terminal")
    st.markdown("---")

    st.header("Scan a Tourist's Digital ID")
    st.info("Upload the QR code image downloaded from the Tourist App to verify the Digital ID.")

    uploaded_file = st.file_uploader("Upload QR Code Image", type=['png', 'jpg', 'jpeg'])

    if uploaded_file is not None:
        from qreader import QReader
        import numpy as np
        import cv2

        with st.spinner("Decoding QR code and running verification checks..."):
            image_bytes = uploaded_file.getvalue()
            nparr = np.frombuffer(image_bytes, np.uint8)
            cv2_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            qreader = QReader()
            decoded_text_list = qreader.detect_and_decode(image=cv2_img)

            if not decoded_text_list or decoded_text_list[0] is None:
                st.error("No QR code could be detected or decoded in the uploaded image.")
            else:
                vc_string = decoded_text_list[0]
                vc_json = json.loads(vc_string)

                st.markdown("---")
                st.header("Verification Results")

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("1. Signature Integrity")
                    is_signature_valid = verify_vc_signature(vc_json.copy())
                    if is_signature_valid:
                        st.success("✅ Signature is Valid")
                    else:
                        st.error("❌ Signature is INVALID")
                with col2:
                    st.subheader("2. Blockchain Anchor")
                    is_anchor_valid = verify_anchor(vc_string)
                    if is_anchor_valid:
                        st.success("✅ Anchor is Verified")
                    else:
                        st.warning("⚠️ Anchor NOT FOUND")

                st.markdown("---")
                if is_signature_valid and is_anchor_valid:
                    st.success("✅ OVERALL STATUS: FULLY VERIFIED")
                    st.balloons()
                else:
                    st.error("❌ OVERALL STATUS: INVALID DIGITAL ID.")

                st.subheader("Verified Tourist Information:")
                tourist_info = vc_json.get('credentialSubject', {}).get('touristInfo', {})
                st.json(tourist_info)


# ==============================================================================
# --- LIVE MONITORING DASHBOARD ---
# ==============================================================================
elif page == "Live Monitoring Dashboard":
    st.title("📡 Live Monitoring Dashboard")
    st.markdown("---")

    st.sidebar.header("Monitoring Controls")
    if st.sidebar.button("Simulate Location Updates"):
        if not st.session_state.tourist_data:
            st.sidebar.warning("No tourists to simulate. Issue an ID first.")
        else:
            with st.spinner("Simulating tourist movements..."):
                # A predefined path: starts safe, goes unsafe, then comes back
                path = [
                    (28.4570, 77.0280), # Safe
                    (28.4700, 77.0600), # Unmonitored
                    (28.441, 77.011),   # RESTRICTED (lat, lon for requests)
                    (28.495, 77.090),   # Point of Interest
                    (28.4560, 77.0270), # Safe
                ]
                for tourist in st.session_state.tourist_data:
                    for i, (lat, lon) in enumerate(path):
                        try:
                            payload = {"latitude": lat, "longitude": lon, "touristId": tourist['id']}
                            requests.post(f"{BACKEND_URL}/api/update_location", json=payload)
                            tourist['lat'], tourist['lon'] = lat, lon
                            st.toast(f"Updating location for {tourist['name']} ({i+1}/{len(path)})...")
                            time.sleep(2) # Pause to make the simulation visible
                        except requests.exceptions.RequestException:
                            st.sidebar.error("Backend not running.")
                            break
                    st.sidebar.success(f"Simulation complete for {tourist['name']}!")

    # --- Map Display ---
    st.header("Live Tourist Locations & Monitored Zones")
    
    # Load the dynamic geo-zones for display
    geo_zones = load_geofences()
    
    if not geo_zones:
        st.warning("Could not load geofences.json. Please make sure the file exists.")
    else:
        # Create a Folium map centered on the general area
        m = folium.Map(location=[28.47, 77.07], zoom_start=12)
        
        # --- Draw all defined zones on the map ---
        zone_colors = {
            "safe_zone": "green",
            "point_of_interest": "blue",
            "restricted_zone": "red"
        }
        for zone in geo_zones:
            folium.Polygon(
                locations=[(lat, lon) for lon, lat in zone['coordinates']], # Folium uses (lat, lon)
                color=zone_colors.get(zone['type'], 'gray'),
                fill=True,
                fill_color=zone_colors.get(zone['type'], 'gray'),
                fill_opacity=0.2,
                tooltip=f"<b>{zone['name']}</b><br>({zone['type']})"
            ).add_to(m)

        # Add tourist markers
        if not st.session_state.tourist_data:
            st.info("No tourists have been issued a Digital ID yet. Go to the Citizen page to issue one.")
        else:
            df = pd.DataFrame(st.session_state.tourist_data)
            for index, row in df.iterrows():
                folium.Marker(
                    location=[row['lat'], row['lon']],
                    popup=f"<b>{row['name']}</b><br>{row['id'][:25]}...",
                    tooltip=row['name'],
                    icon=folium.Icon(color='purple', icon='user')
                ).add_to(m)

        # Display the map in the Streamlit app
        st_folium(m, width=1200, height=600)

