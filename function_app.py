import azure.functions as func
import logging
import requests
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

app = func.FunctionApp()

# Initialize Firebase OUTSIDE the function.
# This ensures it only connects once when the server wakes up, saving memory and time.
firebase_keys_string = os.environ.get("FIREBASE_CREDENTIALS")

# Only initialize if the keys exist and the app hasn't been initialized yet
if firebase_keys_string and not firebase_admin._apps:
    try:
        firebase_keys_dict = json.loads(firebase_keys_string)
        cred = credentials.Certificate(firebase_keys_dict)
        firebase_admin.initialize_app(cred)
        logging.info("Firebase initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize Firebase: {e}")

# The Timer Trigger. Runs every 10 minutes.
@app.timer_trigger(schedule="0 */10 * * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False) 
def warframe_scraper(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info('The timer is past due!')

    logging.info('Warframe Scraper triggered.')

    # 1. Fetch the raw data from Warframe
    url = "https://content.warframe.com/dynamic/worldState.php"
    
    # custom User-Agent so Warframe doesn't block the request as a bot
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # Pass the headers into the request
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # Check for HTTP errors
    
    # try:
    #     response = requests.get(url, timeout=10)
    #     response.raise_for_status() # Check for HTTP errors
        raw_data = response.json()
        
        # 2. Extract just the Alerts (to keep the database clean)
        # The raw JSON has many keys; we only want the 'Alerts' array for now.
        alerts = raw_data.get('Alerts', [])
        
        logging.info(f"Found {len(alerts)} active alerts.")

        # 3. Write to Firestore
        if firebase_admin._apps: # Ensure Firebase actually loaded
            db = firestore.client()
            
            # We overwrite the 'latest' document with the current active alerts
            doc_ref = db.collection('worldState').document('latest')
            doc_ref.set({
                'alerts': alerts,
                'last_updated': firestore.SERVER_TIMESTAMP
            })
            
            logging.info("Successfully updated Firestore with latest Warframe alerts.")
        else:
            logging.error("Cannot write to database. Firebase is not initialized.")

    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch data from Warframe: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")