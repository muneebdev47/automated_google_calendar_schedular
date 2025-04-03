import requests
import json
from datetime import datetime, timedelta, time
from dateutil.parser import isoparse
from dateutil.tz import gettz
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from dotenv import load_dotenv
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import time
import ast
import os

load_dotenv()

# Configuration
CLIENT_SECRET_FILE = os.getenv('CLIENT_SECRET_FILE')
API_KEY = os.getenv('API_KEY')
SCOPES = os.getenv('SCOPES')
token = os.getenv('token')

TIMEZONE = "Europe/Amsterdam"
NETHERLANDS_TZ = gettz(TIMEZONE)
url = "https://klussenvoormij.mrfix.nl/3900"
output_file = "page_content.html"

def authenticate() -> str:
    """Authenticate with OAuth 2.0 and return access token"""
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    return creds.token


def get_free_busy_slots(use_oauth=True):
    """Get free/busy slots from Google Calendar API"""
    now = datetime.utcnow().replace(tzinfo=gettz("UTC"))

    # Set time_min to 8:00 NETHERLANDS_TZ if it hasn't passed yet, otherwise use current time
    today_8am_pkt = datetime.now(NETHERLANDS_TZ).replace(hour=8, minute=0, second=0, microsecond=0)
    today_10pm_pkt = datetime.now(NETHERLANDS_TZ).replace(
        hour=22, minute=0, second=0, microsecond=0
    )

    if datetime.now(NETHERLANDS_TZ) < today_8am_pkt:
        time_min = today_8am_pkt.astimezone(gettz("UTC"))
    else:
        time_min = now

    # time_max = today_10pm_pkt.astimezone(gettz('UTC'))
    time_max = (today_10pm_pkt + timedelta(days=2)).replace(
        hour=22, minute=0, second=0, microsecond=0
    )

    payload = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "timeZone": TIMEZONE,
        "items": [{"id": "primary"}],
    }

    # token = authenticate() if the token expires it can be generated from here

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    response = requests.post(
        "https://www.googleapis.com/calendar/v3/freeBusy", headers=headers, json=payload
    )

    if response.status_code == 200:
        return parse_free_slots(response.json())
    else:
        raise Exception(f"API Error: {response.status_code} - {response.text}")


def parse_free_slots(response_data):
    """Convert busy periods to free slots with proper timezone handling"""
    busy_slots = response_data["calendars"]["primary"].get("busy", [])

    time_min = isoparse(response_data["timeMin"]).astimezone(NETHERLANDS_TZ)
    time_max = isoparse(response_data["timeMax"]).astimezone(NETHERLANDS_TZ)

    free_slots = []
    previous_end = time_min

    for slot in busy_slots:
        slot_start = isoparse(slot["start"]).astimezone(NETHERLANDS_TZ)
        slot_end = isoparse(slot["end"]).astimezone(NETHERLANDS_TZ)

        if slot_start > previous_end:
            clipped_start, clipped_end = clip_to_business_hours(
                previous_end, slot_start
            )

            if clipped_start < clipped_end:
                free_slots.append(
                    {
                        "start": clipped_start.isoformat(),
                        "end": clipped_end.isoformat(),
                        "duration_minutes": int(
                            (clipped_end - clipped_start).total_seconds() / 60
                        ),
                    }
                )

        previous_end = max(previous_end, slot_end)

    if previous_end < time_max:
        clipped_start, clipped_end = clip_to_business_hours(previous_end, time_max)
        if clipped_start < clipped_end:
            free_slots.append(
                {
                    "start": clipped_start.isoformat(),
                    "end": clipped_end.isoformat(),
                    "duration_minutes": int(
                        (clipped_end - clipped_start).total_seconds() / 60
                    ),
                }
            )

    return {
        "timezone": TIMEZONE,
        "time_min": time_min.isoformat(),
        "time_max": time_max.isoformat(),
        "free_slots": free_slots,
        "busy_slots": busy_slots,
    }


def clip_to_business_hours(start, end):
    """Clip time range to business hours (8:00-22:00 NETHERLANDS_TZ)"""
    if start.date() != end.date():
        # For multi-day slots, we'll just consider today's business hours
        end = start.replace(hour=23, minute=59, second=59)

    business_start = start.replace(hour=8, minute=0, second=0)
    business_end = start.replace(hour=22, minute=0, second=0)

    clipped_start = max(start, business_start)
    clipped_end = min(end, business_end)

    if clipped_start >= business_end or clipped_end <= business_start:
        return start.replace(year=1, month=1, day=1), start.replace(
            year=1, month=1, day=1
        )

    return clipped_start, clipped_end


def create_exact_hour_slots(free_slots_response):
    """Create exact hour slots starting on the hour"""
    exact_hour_slots = []

    for slot in free_slots_response["free_slots"]:
        start = isoparse(slot["start"]).astimezone(NETHERLANDS_TZ)
        end = isoparse(slot["end"]).astimezone(NETHERLANDS_TZ)

        if start.minute != 0 or start.second != 0:
            start = start.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=1
            )

        while start + timedelta(hours=1) <= end:
            exact_hour_slots.append(
                {
                    "start": start.isoformat(),
                    "end": (start + timedelta(hours=1)).isoformat(),
                    "duration_minutes": 60,
                }
            )
            start += timedelta(hours=1)

    return {
        "timezone": free_slots_response["timezone"],
        "time_min": free_slots_response["time_min"],
        "time_max": free_slots_response["time_max"],
        "exact_hour_slots": exact_hour_slots,
        "busy_slots": free_slots_response["busy_slots"],
    }


def save_exact_hour_slots(output, filename="exact_hour_slots.py"):
    """Save exact hour slots start times as a list of strings in a Python file"""
    list_of_free_slots = []

    for slot in output["exact_hour_slots"]:
        # Parse and convert to NETHERLANDS_TZ timezone
        start_time = isoparse(slot["start"]).astimezone(NETHERLANDS_TZ)
        # Format as string (e.g., "2025-04-04 09")
        time_str = start_time.strftime("%Y-%m-%d %H")
        list_of_free_slots.append(time_str)

    with open(filename, "w") as file:
        file.write(f"free_slots = {list_of_free_slots}\n")

    print(f"Exact hour slots saved to {filename}")

def get_html(url, output_file):
    try:
        # Send a GET request to the URL
        response = requests.get(url)
        response.raise_for_status()

        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # Get the prettified HTML (formatted with proper indentation)
        pretty_html = soup.prettify()

        # Save the HTML to a file
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(pretty_html)

        print(f"Successfully saved HTML to {output_file}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

def get_links():
    # Read the HTML file
    with open('page_content.html', 'r', encoding='utf-8') as file:
        html_content = file.read()

    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extract all href (excluding "Error" and empty links)
    result_hrefs = [
        a['href'] for a in soup.select('a[href]:not(.text-center a)')
        if a['href'] and a['href'] != 'Error'
    ]

    # Create the Python file content
    joined_hrefs = ',\n    '.join(f'"{href}"' for href in result_hrefs)
    py_content = f"""result_hrefs = [{joined_hrefs}]"""

    # Write to a Python file
    with open('extracted_hrefs.py', 'w', encoding='utf-8') as file:
        file.write(py_content)

    print(f"Found {len(result_hrefs)} hrefs saved to extracted_hrefs.py")

def read_available_slots(filename="exact_hour_slots.py"):
    """Read available slots from Python file and return as list of datetime strings"""
    with open(filename, "r") as file:
        content = file.read()

    # Extract the free_slots list from the Python file
    namespace = {}
    exec(content, namespace)
    free_slots = namespace.get("free_slots", [])

    return free_slots

def read_hrefs(filename="extracted_hrefs.py"):
    with open(filename, "r") as file:
        content = file.read()
    namespace = {}
    exec(content, namespace)
    result_hrefs = namespace.get("result_hrefs", [])

    return result_hrefs

def time_selector(url):
    # Configure Chrome options
    chrome_options = Options()
    chrome_options.headless = False  # Set to True to run in background
    chrome_options.add_argument("--window-size=1920,1080")

    # Initialize the Chrome driver
    driver = webdriver.Chrome(options=chrome_options)

    try:
        # Read available slots from file
        available_slots = read_available_slots()
        if not available_slots:
            raise Exception("No available time slots found in exact_hour_slots.py")

        print(f"Found {len(available_slots)} available time slots:")
        for slot in available_slots:
            print(f"- {slot}")

        # Open the webpage
        driver.get(url)
        print("Opened webpage:", url)

        # Wait for page to load completely
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "date"))
        )
        print("Page loaded successfully")

        # Find the date dropdown
        date_dropdown = driver.find_element(By.NAME, "date")

        # Click to open the dropdown
        date_dropdown.click()
        time.sleep(1)  # Small pause for dropdown to open

        # Create Select object for the dropdown
        date_select = Select(date_dropdown)

        # Try each available slot until we find one that exists in dropdown
        selected = False
        for slot_str in available_slots:
            # The slot is already in "YYYY-MM-DD HH" format
            try:
                # Try to find matching option in dropdown
                for option in date_select.options:
                    if slot_str in option.get_attribute("value"):
                        date_select.select_by_value(option.get_attribute("value"))
                        print(f"Successfully selected time slot: {slot_str}")
                        selected = True
                        break
                if selected:
                    print("selected slot is: ", slot_str)
                    break
            except Exception as e:
                print(f"Error selecting slot {slot_str}: {str(e)}")
                continue

        if not selected:
            raise Exception(
                "None of the available slots from file were found in the dropdown"
            )

        # 2. HOURS SELECTION - Select "1-2" hours option
        hours_select = Select(driver.find_element(By.NAME, "hours"))
        hours_select.select_by_value("1-2")
        print("Selected hours: 1-2")

        # 3. FORM SUBMISSION
        submit_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit'][value='Verzend']"))
        )

        # Scroll to the button to ensure it's visible
        driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
        time.sleep(0.5)

        # Click the submit button
        submit_button.click()
        print("Form submitted successfully")


    except Exception as e:
        print(f"An error occurred: {str(e)}")
        # Take screenshot if there's an error
        driver.save_screenshot("error_screenshot.png")
        print("Screenshot saved as error_screenshot.png")

    finally:
        # Close the browser
        driver.quit()
        print("Browser closed")
        return slot_str

def remove_slot_from_file(slot_to_remove, filename="exact_hour_slots.py"):
    """
    Remove a time slot string from the free_slots list in the Python file
    
    Args:
        slot_to_remove (str): The slot to remove (e.g., "2025-04-04 09")
        filename (str): Path to the Python file containing the free_slots list
    
    Returns:
        bool: True if slot was found and removed, False otherwise
    """
    try:
        # Read the file content
        with open(filename, 'r') as file:
            content = file.read()
        
        # Parse the file to get the free_slots list
        namespace = {}
        exec(content, namespace)
        free_slots = namespace.get('free_slots', [])
        
        # Check if slot exists and remove it
        if slot_to_remove in free_slots:
            free_slots.remove(slot_to_remove)
            
            # Rebuild the file content
            new_content = f"free_slots = {free_slots}"
            
            # Write back to the file
            with open(filename, 'w') as file:
                file.write(new_content)
            
            return True
        return False
    
    except Exception as e:
        print(f"Error updating slots file: {e}")
        return False

def create_calendar_event(
    start_time: datetime,
    summary: str = "Testing Event",
    description: str = "hello this is a testing event",
    attendees: list = None,
    location: str = None,
    create_meet: bool = False,
    reminders: dict = None,
    token: str = None,
):
    """
    Create an event on Google Calendar

    Args:
        start_time (datetime): Event start time in NETHERLANDS_TZ
        end_time (datetime): Event end time in NETHERLANDS_TZ
        summary (str): Event title
        description (str): Event description
        attendees (list): List of email addresses
        location (str): Physical location
        create_meet (bool): Whether to create Google Meet link
        reminders (dict): Reminder settings
        token (str): OAuth2 token

    Returns:
        dict: Created event details
    """
    # Convert NETHERLANDS_TZ times to UTC for API
    end_time = start_time + timedelta(hours=1)
    start_utc = start_time.astimezone(gettz("UTC"))
    end_utc = end_time.astimezone(gettz("UTC"))

    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_utc.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_utc.isoformat(), "timeZone": "UTC"},
        "reminders": {"useDefault": True},
    }

    # Optional parameters
    if attendees:
        event["attendees"] = [{"email": email} for email in attendees]

    if location:
        event["location"] = location

    if create_meet:
        event["conferenceData"] = {
            "createRequest": {
                "requestId": f"meet_{start_time.timestamp()}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    if reminders:
        event["reminders"] = reminders

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    params = {"conferenceDataVersion": 1 if create_meet else 0}

    response = requests.post(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers=headers,
        params=params,
        json=event,
    )

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"API Error: {response.status_code} - {response.text}")


if __name__ == "__main__":
    try:
        print("Fetching calendar availability...")
        result = get_free_busy_slots(use_oauth=True)

        print("\nFree Slots in NETHERLANDS_TZ (8:00-22:00):")
        for slot in result["free_slots"]:
            start = isoparse(slot["start"]).astimezone(NETHERLANDS_TZ).strftime("%Y-%m-%d %H:%M")
            end = isoparse(slot["end"]).astimezone(NETHERLANDS_TZ).strftime("%Y-%m-%d %H:%M")
            print(f"{start} to {end} ({slot['duration_minutes']} minutes)")


        output = create_exact_hour_slots(result)
        save_exact_hour_slots(output)
        get_html(url, output_file)
        get_links()
        post_links = read_hrefs()
        for url in post_links:
            selected_slot = time_selector(url)
            remove_slot_from_file(selected_slot)
            selected_slot = isoparse(selected_slot).astimezone(NETHERLANDS_TZ)
            create_calendar_event(start_time=selected_slot, token=token)

    except Exception as e:
        print(f"Error: {str(e)}")
