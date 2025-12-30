
import re
import dateparser
from datetime import datetime, date, timedelta
from rapidfuzz import process, fuzz

class SmartParser:
    def __init__(self):
        # 1. Zone Synonyms (Keywords -> Real Zone Name)
        self.zone_map = {
            "gym": "Gym", "court": "Gym", "basketball": "Gym",
            "canteen": "Canteen", "cafeteria": "Canteen", "food": "Canteen", "lunch": "Canteen",
            "library": "Library", "books": "Library", "study": "Library",
            "admin": "Admin Office", "office": "Admin Office", "principal": "Admin Office",
            "hall": "Main Hall", "lobby": "Main Hall", "entrance": "Main Hall",
            "class": "Classrooms", "room": "Classrooms", "lecture": "Classrooms",
            "corridor": "Corridor", "hallway": "Corridor",
            "everyone": "All Zones", "all": "All Zones", "campus": "All Zones", "school": "All Zones"
        }

        # 2. Template Responses (Keyword -> Professional Message)
        self.templates = {
            # --- EMERGENCY & SAFETY ---
            "fire": "Attention all zones. This is a Fire Drill. Please calmly proceed to the nearest exit.",
            "earthquake": "Earthquake Alert. Duck, Cover, and Hold. Please go to the open grounds.",
            "flood": "Weather Alert. Heavy rain expected. Please prepare for evacuation if necessary.",
            "lockdown": "Security Alert. Campus Lockdown initiated. Please remain inside and lock all doors.",
            "evacuate": "Emergency Evacuation. Please leave the building immediately via the nearest exit.",
            "medical": "Medical Emergency reported. Response team, please proceed immediately.",
            "all clear": "The Emergency situation has ended. All Clear. You may resume normal activities.",
            
            # --- SCHOOL ROUTINE ---
            "flag": "Please proceed to the Main Hall for the Flag Ceremony.",
            "anthem": "Please stand for the National Anthem.",
            "assembly": "Attention all students and staff. Please proceed to the assembly area.",
            "dismissal": "Classes are now dismissed. Please proceed to the gates in an orderly manner.",
            "recess": "It is now time for Recess. Please enjoy your break.",
            "lunch": "It is now time for the Lunch Break. Please enjoy your meal.",
            "exam start": "Examination period has started. Please maintain silence in all corridors.",
            "exam end": "The examination period has ended. Please pass your papers.",
            "silence": "Assessment in progress. Please maintain silence in all areas.",

            # --- CAMPUS OPERATIONS ---
            "welcome": "Good morning. We welcome all visitors to our campus. Please proceed to the Admin Office.",
            "closing": "The campus will be closing shortly. Please finalize your activities.",
            "library closing": "Library Closing Announcement: The library will be closing in 15 minutes.",
            "bus": "School Bus Announcement: The buses have arrived at the waiting area.",
            "gate": "Gate Announcement: The main gates will be closing in 10 minutes.",
            "late": "Reminder: Latecomers, please proceed to the guidance office for your slip.",
            
            # --- MAINTENANCE & UTILITIES ---
            "clean": "Sanitization in progress. Please keep the area clear.",
            "sanitiz": "Sanitization in progress. Please keep the area clear.",
            "maintenance": "Maintenance Work in progress. Please exercise caution in the affecting area.",
            "power": "Advisory: Scheduled power interruption will occur shortly. Please save your work.",
            "water": "Advisory: Water service interruption reported. Maintenance is ongoing.",
            "internet": "IT Advisory: Internet maintenance is currently ongoing. Connection may be intermittent.",

            # --- GENERAL ---
            "lost": "Announcement: An item has been found. Please visit the Lost and Found office.",
            "found": "Announcement: An item has been found. Please visit the Lost and Found office.",
            "meeting": "Attention Staff. There will be a meeting in the Admin Office.",
            "congrats": "Congratulations to our students for their achievement! We are proud of you.",
            "test": "This is a test of the Public Address System. Thank you.",
            
            # --- EVENTS & ALERTS ---
            "suspension": "Advisory: Classes are suspended due to inclement weather. Please go home safely.",
            "resume": "Advisory: Classes will resume as scheduled.",
            "parking": "Vehicle owner alert: Please move your vehicle from the prohibited parking area.",
            "noise": "Reminder: Please maintain minimal noise levels in the corridors.",
            "id": "Reminder: Wearing of School ID is mandatory within campus premises.",
            "uniform": "Reminder: Please be in complete school uniform.",
            "program": "The program is about to start. Please take your seats.",
            "guest": "We are honored to have special guests on campus. Please show them our hospitality.",
            "curfew": "Campus Curfew is approaching. Please vacate the premises.",
            "clinic": "Health Advisory: Please visit the clinic if you are feeling unwell.",

            # --- FACULTY & ACADEMICS ---
            "deadline": "Reminder to all students: Today is the deadline for submission of requirements.",
            "grades": "Attention Faculty: Please submit your grading sheets to the Admin Office.",
            "clearance": "Reminder: Please settle your clearance at the Registrar's Office.",
            "enrollment": "Enrollment is now ongoing. Please proceed to the designated windows.",
            
            # --- ACTIVITIES ---
            "club": "Club activities will begin shortly. Please proceed to your designated rooms.",
            "practice": "Varsity practice is scheduled to start. Team members, please proceed to the Gym.",
            "rehearsal": "Rehearsal for the upcoming event is now starting. Please assemble at the venue.",
            "varsity": "Calling all Varsity players. Please report to the Gym immediately."
        }

    def parse_command(self, text: str, user_zones: list = None) -> dict:
        """
        Parses commands using Fuzzy Logic (Level 2).
        """
        result = {
            "message": "",
            "date": None,
            "time": None,
            "repeat": "none",
            "zones": []
        }

        # Pre-cleaning: Remove likely garbage characters if any, but keep structure
        lower_text = text.lower()


        # --- STEP 1: TIME EXTRACTION (Regex & Relative) ---
        # 1. Try Strict Regex first: 9:30, 09:30, 9:30am, 9am, 5pm
        strict_time_match = re.search(r'(\d{1,2})(:(\d{2}))?\s*(am|pm)', lower_text)
        
        # 2. Try Relative Regex: "in 10 minutes", "in 1 hour"
        relative_time_match = re.search(r'in\s+(\d+)\s*(min|minute|hour|hr)s?', lower_text)

        parsed_time_obj = None

        if strict_time_match:
            raw_time = strict_time_match.group(0)
            parsed_time_obj = dateparser.parse(raw_time)
        elif relative_time_match:
            # "in 10 minutes" -> Let dateparser handle the calculation from NOW
            raw_relative = relative_time_match.group(0)
            parsed_time_obj = dateparser.parse(raw_relative)
        elif "now" in lower_text:
            parsed_time_obj = datetime.now()

        if parsed_time_obj:
            result['time'] = parsed_time_obj.strftime("%H:%M")
            # If we found a time, IMPLY 'Today' if no other date is found later
            if not result['date']:
                 result['date'] = date.today().strftime("%Y-%m-%d")


        # --- STEP 2: DATE EXTRACTION (Dateparser) ---
        # Strip out the explicit time part first to avoid dateparser testing strings with numbers as dates
        text_without_time = lower_text
        if strict_time_match:
            text_without_time = lower_text.replace(strict_time_match.group(0), "")
        if relative_time_match:
            text_without_time = lower_text.replace(relative_time_match.group(0), "")

        date_keywords = ["tomorrow", "next", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "today", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
        
        if any(w in lower_text for w in date_keywords):
            settings = {'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': datetime.now()}
            parsed_date = dateparser.parse(text_without_time, settings=settings)
            
            if parsed_date:
                result['date'] = parsed_date.strftime("%Y-%m-%d")
        
        if result['time'] and not result['date']:
             result['date'] = date.today().strftime("%Y-%m-%d")


        # --- STEP 3: REPEAT EXTRACTION ---
        if "daily" in lower_text or "every day" in lower_text:
            result['repeat'] = "daily"
        elif any(phrase in lower_text for phrase in ["weekly", "every week", "every mon", "every tue", "every wed", "every thu", "every fri", "every sat", "every sun"]):
            result['repeat'] = "weekly"


        # --- STEP 4: ZONE EXTRACTION (FUZZY) ---
        found_zones = []
        # Split text into words to check against zones? or just fuzzy search the whole text against keys?
        # Fuzzy searching "whole text" against "small keyword" is tricky.
        # Better: Iterate keys, and see if key is "partial match" in text with high confidence.
        # RapidFuzz partial_ratio is good for "is 'gym' inside 'go to the gymnow'?"
        
        for keyword, zone_name in self.zone_map.items():
            # partial_ratio: finds best matching substring
            score = fuzz.partial_ratio(keyword, lower_text) 
            if score > 85: # High confidence for short words like "gym"
                if zone_name not in found_zones:
                    found_zones.append(zone_name)
        
        if "All Zones" in found_zones:
            result['zones'] = ["All Zones"]
        else:
            result['zones'] = found_zones


        # --- STEP 5: MESSAGE TEMPLATES (FUZZY) ---
        # Find the BEST matching template keyword in the text
        # We process the text against our list of keys? No, we check if any KEY is in the TEXT.
        # But for Fuzzy, we want to see if 'Frie Drill' (User input) matches 'fire' (Key).
        
        # Strategy: Extract words from user input, and check if any word matches a template key?
        # Or: Check each template key against the whole text using partial_ratio.
        
        best_match_score = 0
        best_match_template = ""
        
        for keyword, template in self.templates.items():
            # Check if this keyword exists in the text (Fuzzily)
            score = fuzz.partial_ratio(keyword, lower_text)
            
            # Boost score for exact matches or near-exact
            if score > 80: # Threshold for "Yeah, that's probably it"
                if score > best_match_score:
                    best_match_score = score
                    best_match_template = template
        
        if best_match_template:
            result['message'] = best_match_template
        
        
        # --- STEP 6: FALLBACK MESSAGE ---
        if not result['message']:
            clean_text = re.sub(r'^(please\s+)?(announce|say|tell|broadcast)\s+(that\s+)?', '', text, flags=re.IGNORECASE)
            clean_text = clean_text[0].upper() + clean_text[1:] if clean_text else ""
            result['message'] = clean_text

        # Defaults if empty
        if not result['zones']:
             result['zones'] = ["All Zones"]

        return result

smart_parser = SmartParser()
