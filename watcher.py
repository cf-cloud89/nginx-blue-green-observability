import os
import time
import json
import requests
from collections import deque

# --- 1. Load Configuration from Environment Variables ---

# Slack webhook URL (secret)
SLACK_URL = os.getenv("SLACK_WEBHOOK_URL")
# Path to the log file, set by our Docker volume
LOG_FILE = "/var/log/nginx/access.log"

# App state
# Start with the default pool
last_seen_pool = os.getenv("ACTIVE_POOL", "blue")

# Alerting thresholds
# We read them as strings and convert to numbers
try:
    ERROR_THRESHOLD = float(os.getenv("ERROR_RATE_THRESHOLD", 2))
    WINDOW_SIZE = int(os.getenv("WINDOW_SIZE", 200))
    COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", 300))
    MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
except ValueError:
    print("Error: Invalid threshold environment variables. Using defaults.")
    ERROR_THRESHOLD = 2.0
    WINDOW_SIZE = 200
    COOLDOWN_SEC = 300
    MAINTENANCE_MODE = False

# --- 2. State and Alerting Logic ---

# Rolling window for error rate calculation
requests_window = deque(maxlen=WINDOW_SIZE)

# Cooldown to prevent alert spam
last_alert_time = {
    "failover": 0,
    "error_rate": 0,
    "recovery": 0  # <--- FIX 1: Add a separate cooldown timer for recovery
}

def send_slack_alert(message_type, message):
    """
    Sends a formatted alert to Slack, respecting cooldowns.
    """
    global last_alert_time
    
    if MAINTENANCE_MODE:
        print(f"MAINTENANCE MODE: Suppressed alert for {message_type}")
        return

    current_time = time.time()
    
    # Check if we are in a cooldown period for this alert type
    if current_time - last_alert_time[message_type] < COOLDOWN_SEC:
        print(f"COOLDOWN: Suppressed alert for {message_type}")
        return

    if not SLACK_URL:
        print(f"ALERT (Dry Run - No Webhook): {message}")
        return

    try:
        # Format the Slack message
        payload = {
            "attachments": [{
                "color": "#ff0000" if message_type == "error_rate" else ("#00ff00" if message_type == "recovery" else "#ffaa00"),
                "title": f" Nginx Alert: {message_type.replace('_', ' ').title()}",
                "text": message,
                "ts": current_time
            }]
        }
        requests.post(SLACK_URL, json=payload, timeout=5)
        last_alert_time[message_type] = current_time # Update last alert time
        print(f"ALERT SENT: {message_type}")
    except Exception as e:
        print(f"Error sending Slack alert: {e}")

def analyze_log_line(log_data):
    """
    Analyzes a single parsed log line for failovers and errors.
    """
    global last_seen_pool, requests_window

    # --- 1. Failover Detection ---
    current_pool = log_data.get("pool")
    if current_pool and current_pool != last_seen_pool:
        # We've detected a pool flip!
        alert_msg = f"Traffic has flipped from '{last_seen_pool}' to '{current_pool}'."
        if last_seen_pool == os.getenv("ACTIVE_POOL", "blue"):
            send_slack_alert("failover", f"FAILOVER DETECTED: {alert_msg}")
        else:
            # FIX 1: Use the "recovery" message_type so it bypasses the "failover" cooldown
            send_slack_alert("recovery", f"RECOVERY: {alert_msg}")
        last_seen_pool = current_pool

    # --- 2. Error Rate Detection ---
    
    # FIX 2: Make this parsing logic safer to avoid crashes on 'None'
    upstream_status_str = log_data.get("upstream_status") # Get value, might be None
    
    if not upstream_status_str:
        upstream_status_str = "200" # Default to "200" if field is missing or null

    # $upstream_status can be "502, 200"
    # We only care about the first status, which is the primary attempt
    first_status = upstream_status_str.split(",")[0].strip() # "502" or "200"

    # Check if the status code is a 5xx server error
    is_5xx_error = first_status.startswith("5")
    
    # Add to our rolling window
    requests_window.append(is_5xx_error)

    # Only calculate if the window is full
    if len(requests_window) == WINDOW_SIZE:
        error_count = sum(1 for is_error in requests_window if is_error)
        error_rate = (error_count / WINDOW_SIZE) * 100
    
        if error_rate > ERROR_THRESHOLD:
            alert_msg = (
                f"High upstream 5xx error rate detected: "
                f"**{error_rate:.2f}%** over the last {WINDOW_SIZE} requests "
                f"(Threshold: {ERROR_THRESHOLD}%)."
            )
            send_slack_alert("error_rate", alert_msg)

def tail_log_file():
    """
    "Tails" the log file and processes new lines as they appear.
    """
    print("Log watcher started. Tailing log file...")
    # Check for the file to exist (Nginx might take a sec to create it)
    while not os.path.exists(LOG_FILE):
        print("Log file not found, sleeping 5s...")
        time.sleep(5)
        
    with open(LOG_FILE, 'r') as f:
        # Go to the end of the file
        f.seek(0, 2)
        
        while True:
            line = f.readline()
            if not line:
                # No new line, wait a bit
                time.sleep(0.1)
                continue
            
            try:
                # Parse the JSON log line
                log_data = json.loads(line)
                analyze_log_line(log_data)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse log line: {line.strip()}")
            except Exception as e:
                print(f"Error processing line: {e}")

if __name__ == "__main__":
    if MAINTENANCE_MODE:
        print("--- MAINTENANCE MODE IS ACTIVE. NO ALERTS WILL BE SENT. ---")
    
    if not SLACK_URL:
        print("--- WARNING: SLACK_WEBHOOK_URL is not set. Will print alerts to console. ---")

    tail_log_file()
