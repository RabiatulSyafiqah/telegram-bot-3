# sheet.py
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from googleapiclient.discovery import build
import os
import json

# === SETTINGS ===
SHEET_NAME = "PDK_Appointment_Bookings"
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']
OFFICE_HOURS = {
    'Monday':    ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30','14:00', '14:30', '15:00', '15:30', '16:00'],
    'Tuesday':   ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30','14:00', '14:30', '15:00', '15:30', '16:00'],
    'Wednesday': ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30','14:00', '14:30', '15:00', '15:30', '16:00'],
    'Thursday':  ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30','14:00', '14:30', '15:00', '15:30', '16:00'],
    'Friday':    ['09:00', '09:30', '10:00', '10:30','14:00', '14:30', '15:00', '15:30', '16:00'],
}
OFFICER_CALENDARS = {
    "DO": "do@keningau.gov.my",
    "ADO": "rabiatulsyafiqahhh@gmail.com"
}

# === GOOGLE SHEETS & CALENDAR AUTH ===
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    *CALENDAR_SCOPES
]

google_creds_json = os.getenv("GOOGLE_CREDS_JSON")
creds = None
if not google_creds_json:
    print("[WARNING] GOOGLE_CREDS_JSON environment variable is missing. Google integrations disabled.")
else:
    try:
        creds_dict = json.loads(google_creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in GOOGLE_CREDS_JSON: {e}")
        creds = None

try:
    if creds:
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
    else:
        sheet = None
except Exception as e:
    print(f"[ERROR] Failed to access Google Sheet: {e}")
    sheet = None

try:
    if creds:
        calendar_service = build('calendar', 'v3', credentials=creds)
    else:
        calendar_service = None
except Exception as e:
    print(f"[ERROR] Calendar service initialization failed: {e}")
    calendar_service = None

# === HELPERS ===
def is_valid_date(date_str):
    try:
        day, month, year = map(int, date_str.split('/'))
        input_date = datetime(year, month, day).date()
        return input_date >= datetime.now().date()
    except (ValueError, TypeError, AttributeError):
        return False

def is_weekend(date_str):
    try:
        day, month, year = map(int, date_str.split('/'))
        date_obj = datetime(year, month, day)
        return date_obj.weekday() >= 5
    except (ValueError, TypeError, AttributeError):
        return False

def get_available_slots(date_str):
    if not sheet:
        return []
    try:
        day, month, year = map(int, date_str.split('/'))
        weekday = datetime(year, month, day).strftime('%A')
        return OFFICE_HOURS.get(weekday, [])
    except (ValueError, TypeError, AttributeError):
        return []

def is_slot_available(date, time, officer):
    if not sheet:
        return False
    if not is_valid_date(date) or is_weekend(date):
        return False
    records = sheet.get_all_records()
    for row in records:
        if row['Date'] == date and row['Time'] == time and row['Officer'] == officer:
            return False
    return True

def create_calendar_event(officer, date_str, time_str, user_name, purpose, phone):
    if not calendar_service:
        return None
    try:
        day, month, year = map(int, date_str.split('/'))
        date_obj = datetime(year, month, day)
        start_time = datetime.strptime(time_str, '%H:%M')
        end_time = start_time + timedelta(minutes=30)

        start_datetime = datetime.combine(date_obj, start_time.time()).isoformat() + '+08:00'
        end_datetime = datetime.combine(date_obj, end_time.time()).isoformat() + '+08:00'

        event = {
            'summary': f'Temu Janji: {user_name}',
            'description': f'Tujuan: {purpose}\nNo. Telefon: {phone}',
            'start': {'dateTime': start_datetime},
            'end': {'dateTime': end_datetime},
            'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 30}]}
        }

        return calendar_service.events().insert(calendarId=OFFICER_CALENDARS[officer], body=event).execute()
    except Exception as e:
        print(f"[ERROR] Calendar error: {e}")
        return None

def save_booking(user_id, name, phone, email, officer, purpose, date, time):
    if not sheet:
        print("[ERROR] Cannot save booking: Google Sheet not available.")
        return
    sheet.append_row([user_id, name, phone, email, officer, purpose, date, time, "CONFIRMED"])
    event = create_calendar_event(officer, date, time, name, purpose, phone)
    if event:
        print(f"✅ Calendar event created: {event.get('htmlLink')}")
    else:
        print("[WARNING] Booking saved to sheet, but calendar event failed.")
