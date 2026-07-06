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

   # 1. Fetch the data from the community API (Bypasses Cloudflare IP blocks)
    # Note: Using '/pc to get all the data and sift it from there as needed
    url = "https://api.warframestat.us/pc"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10) #send request with a timeout
        response.raise_for_status() # Check for HTTP errors
        
        # 2. Parse the info into a json object
        world_state = response.json()
        
        # 3. Pluck out only the arrays we care about right now
        # The .get() method is safe: if 'alerts' is missing, it returns an empty array []
        alerts = world_state.get('alerts', []) #basically asking for info in using a key -> 'alerts'
        fissures = world_state.get('fissures', [])
        # arbitration = world_state.get('arbitration', {}) #gets junk data every time

        #baro ki'teer
        void_trader = world_state.get('voidTrader', {})

        #world cycles
        cetus = world_state.get('cetusCycle', {})
        vallis = world_state.get('vallisCycle', {})
        cambion = world_state.get('cambionCycle', {})
        duviri = world_state.get('duviriCycle', {})

        #syndicate missions
        raw_syndicate_missions = world_state.get('syndicateMissions', [])
        target_syndicates = [
            "Ostrons", 
            "Solaris United",
            "EntratiSyndicate", 
            "Entrati",
        ]
        cleaned_syndicate_missions = []

        for syndicate in raw_syndicate_missions:
            syndicate_id = syndicate.get('id', '')
            syndicate_key = syndicate.get('syndicateKey', '')
            
            # Keep only the target syndicates
            if syndicate_key in target_syndicates or any(target in syndicate_id for target in target_syndicates):
                
                # Prune the bloated reward arrays from each job
                if 'jobs' in syndicate:
                    for job in syndicate['jobs']:
                        job.pop('rewardPool', None)
                        job.pop('rewardPoolDrops', None)
                
                cleaned_syndicate_missions.append(syndicate)

        #End-Game Weekly Missions
        sortie = world_state.get('sortie', {})
        archon_hunt = world_state.get('archonHunt', {})

        #Faction invasion events
        #fomorion and razorback armada
        construction_progress = world_state.get('constructionProgress', [])
        #invasion battles
        invasions = world_state.get('invasions', [])

        #logging.info(f"Found {len(alerts)} active alerts.")
        logging.info(f"Found {len(alerts)} active alerts and {len(fissures)} active fissures.")

        # 4. Write to Firestore
        if firebase_admin._apps: 
            db = firestore.client()
            
            doc_ref = db.collection('worldState').document('latest')
            doc_ref.set({
                'alerts': alerts,
                'fissures': fissures,
                # 'arbitration': arbitration,
                'voidTrader': void_trader,
                'cetusCycle': cetus,
                'vallisCycle': vallis,
                'cambionCycle': cambion,
                'duviriCycle': duviri,
                'sortie': sortie,
                'archonHunt': archon_hunt,
                'constructionProgress': construction_progress,
                'invasions': invasions,
                'syndicateMissions': cleaned_syndicate_missions,
                'last_updated': firestore.SERVER_TIMESTAMP
            })
            
            logging.info("Successfully updated Firestore with latest Warframe alerts.")
        else:
            logging.error("Cannot write to database. Firebase is not initialized.")

    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch data from Warframe: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")