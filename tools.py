# tools.py
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import traceback # Importing traceback for detailed error logging

# --- Google Sheets Setup ---
# Define the scope of permissions
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file']

# IMPORTANT: Ensure this filename matches the JSON key file in your 'credentials' folder.
CREDS_FILE = 'credentials/ai-bus-agent-12345-a1b2c3d4e5f6.json' 

# --- Your Specific Google Sheet ID ---
# This is a more reliable way to open the sheet than using its name.
SHEET_ID = '1YNVgp9OlLOfLd3ZTqs8SAEWNOpqP88GHrqjenAZqzp4'

sheet = None # Initialize sheet as None

# --- Connection Block ---
try:
    print("Attempting to connect to Google Sheets...")
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
    client = gspread.authorize(creds)
    
    print(f"Successfully authorized. Opening sheet by ID: '{SHEET_ID}'...")
    # Open the sheet using its unique ID.
    spreadsheet = client.open_by_key(SHEET_ID)
    sheet = spreadsheet.sheet1
    print("Successfully connected to Google Sheet.")

except gspread.exceptions.SpreadsheetNotFound:
    print("FATAL ERROR: SpreadsheetNotFound. This means the service account does not have permission for this specific SHEET_ID, or the ID is incorrect.")
    print("ACTION: Double-check that you have shared your Google Sheet with the client_email as an 'Editor'.")
except Exception as e:
    print("---------- DETAILED FATAL ERROR ----------")
    print(f"An unexpected error occurred: {e}")
    traceback.print_exc()
    print("----------------------------------------")
# --- End of Connection Block ---


def find_bus_for_stop(stop_name):
    """
    Finds bus details for a given stop name by searching the College Bus Routes Google Sheet.
    Returns a JSON string with the bus details or an error message if not found.
    """
    if not sheet:
        # This will be returned if the initial connection failed
        return json.dumps({"error": "Sorry, the bus schedule service is temporarily unavailable due to a configuration error."})
    
    try:
        # Get all rows from the sheet as a list of dictionaries
        records = sheet.get_all_records()
        for row in records:
            # Check if the user's stop_name is part of the text in the 'StopName' column.
            if stop_name.lower() in str(row.get('StopName', '')).lower():
                # Found the stop, return all details for that row
                return json.dumps(row)
        
        # If the loop finishes without finding the stop
        return json.dumps({"error": "Sorry, I could not find a bus for that stop. Please try saying the name of the stop again."})
    except Exception as e:
        print(f"Error during sheet search: {e}")
        return json.dumps({"error": "Sorry, I'm having trouble accessing the bus schedule right now."})

# Define the schema for the tool that the OpenAI model will see.
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "find_bus_for_stop",
            "description": "Get the bus details (Serial Number, Driver Name, etc.) for a specific stop name provided by a student.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stop_name": {
                        "type": "string",
                        "description": "The name of the bus stop the student wants to go to, e.g., 'Main Market', 'Sector 15', 'Vijay Nagar'."
                    }
                },
                "required": ["stop_name"]
            }
        }
    }
]

# A dictionary to map the function name to the actual Python function.
available_functions = {
    "find_bus_for_stop": find_bus_for_stop,
}