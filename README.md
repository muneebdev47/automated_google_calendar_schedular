# Google Calendar Automation Tool - Documentation

## Overview
This tool automates the process of finding available time slots in your Google Calendar, selecting them on a booking website, and creating corresponding calendar events. It's designed for the Netherlands timezone (Europe/Amsterdam).

## Configuration
The script uses environment variables stored in a `.env` file:
```env
CLIENT_SECRET_FILE=path/to/client_secret.json
API_KEY=your_google_api_key
SCOPES=https://www.googleapis.com/auth/calendar
token=your_access_token
```

## Core Functions

### 1. Authentication
**`authenticate() -> str`**  
- Handles OAuth 2.0 authentication with Google Calendar API
- Returns an access token for API requests
- Opens a browser window for user consent on first run

### 2. Free/Busy Slot Management

**`get_free_busy_slots(use_oauth=True)`**  
- Retrieves free/busy information from Google Calendar
- Focuses on business hours (8:00-22:00 Netherlands time)
- Returns time slots for the current day and next two days
- Uses OAuth by default but can fall back to API key

**`parse_free_slots(response_data)`**  
- Processes raw Google Calendar API response
- Converts UTC times to Netherlands timezone
- Filters to only include business hours
- Calculates duration of each free slot

**`clip_to_business_hours(start, end)`**  
- Helper function that adjusts time ranges to fit within business hours
- Ensures all slots are between 8:00 and 22:00

### 3. Slot Processing

**`create_exact_hour_slots(free_slots_response)`**  
- Takes free slots and converts them to exact hour slots
- Rounds start times to the nearest hour
- Ensures each slot is exactly 1 hour long
- Returns structured data with timezone information

**`save_exact_hour_slots(output, filename)`**  
- Saves available hour slots to a Python file
- Stores slots in format: `["2025-04-04 09", "2025-04-04 10", ...]`
- Creates a file that can be imported by other scripts

**`remove_slot_from_file(slot_to_remove, filename)`**  
- Removes a booked time slot from the saved slots file
- Maintains the integrity of the remaining slots
- Returns True if slot was found and removed

### 4. Web Scraping & Automation

**`get_html(url, output_file)`**  
- Downloads HTML content from a given URL
- Uses BeautifulSoup to parse and prettify the HTML
- Saves cleaned HTML to a local file

**`get_links()`**  
- Extracts all href links from saved HTML
- Filters out empty and "Error" links
- Saves valid links to a Python file as a list

**`read_hrefs(filename)`**  
- Reads the saved links from a Python file
- Returns them as a Python list for processing

### 5. Web Interaction

**`time_selector(url)`**  
- Automates time slot selection on the booking website
- Uses Selenium to interact with the webpage
- Matches available calendar slots with website options
- Handles form submission
- Returns the selected time slot string

### 6. Calendar Event Creation

**`create_calendar_event(start_time, ...)`**  
- Creates a 1-hour Google Calendar event
- Converts Netherlands time to UTC for API
- Supports optional parameters:
  - Meeting title and description
  - Attendees list
  - Location
  - Google Meet creation
  - Custom reminders
- Returns the created event details

## Main Workflow

1. **Fetch Availability**  
   - Calls `get_free_busy_slots()` to get calendar availability
   - Processes results with `parse_free_slots()`

2. **Process Slots**  
   - Creates exact hour slots with `create_exact_hour_slots()`
   - Saves slots to file with `save_exact_hour_slots()`

3. **Web Scraping**  
   - Downloads booking page HTML with `get_html()`
   - Extracts available links with `get_links()`

4. **Automated Booking**  
   - For each booking link:
     - Selects time slot with `time_selector()`
     - Removes booked slot with `remove_slot_from_file()`
     - Creates calendar event with `create_calendar_event()`

## Error Handling
- Comprehensive error handling throughout
- Screenshots saved on web automation failures
- Clear error messages for API failures
- Graceful handling of missing slots or links

## Dependencies
- Python 3.6+
- Required packages:
  - `requests`, `python-dotenv`, `beautifulsoup4`
  - `selenium`, `dateutil`, `google-auth`

## Timezone Handling
All times are processed in Europe/Amsterdam timezone (NETHERLANDS_TZ) and converted to UTC only for API communication. The system automatically handles daylight saving time changes.