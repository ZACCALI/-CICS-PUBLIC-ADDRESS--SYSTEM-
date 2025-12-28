
import os
import json
import google.generativeai as genai
from datetime import datetime, date
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SmartParser:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("WARNING: GEMINI_API_KEY not found in environment variables.")
        else:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-flash-latest')

    def parse_command(self, text: str, user_zones: list = None) -> dict:
        """
        Parses a natural language scheduling command into structured JSON.
        
        Args:
            text: The user's command string.
            user_zones: Optional list of available zones for validation/matching.
            
        Returns:
            dict: { "message": str, "date": str (YYYY-MM-DD), "time": str (HH:MM), "repeat": str, "zones": list }
        """
        if not hasattr(self, 'model'):
            return {"error": "AI Service not configured (Missing API Key)."}

        today_str = date.today().isoformat()
        current_time_str = datetime.now().strftime("%H:%M")
        
        zones_hint = f"Available zones: {', '.join(user_zones)}" if user_zones else "Zones: Gym, Corridor, Canteen, Lobby, Library, etc."

        prompt = f"""
        You are a smart scheduling assistant for a school PA system.
        Today is {today_str}, and the current time is {current_time_str}.
        
        Your task is to extract the following information from the user's command:
        - message: Generate a clear, polite, and complete announcement sentence based on the command. If the input is short (e.g. "Sanitization"), expand it into a proper sentence (e.g. "Please be advised that sanitization will take place"). Do not include "Announce" or "Say" in the output.
        - date: The date in YYYY-MM-DD format. Calculate relative dates (e.g. "next Friday", "tomorrow"). If no date is mentioned, return null. 
        - time: The time in HH:MM (24-hour) format. If no time is mentioned, return null.
        - repeat: 'None', 'Daily', 'Weekly', or 'Monthly'. Default is 'None'.
        - zones: A list of zone names. If "everyone", "all", or "campus" is mentioned, return ["All Zones"]. If specific zones are mentioned, list them. If no zones are mentioned, return null (do not guess).
        
        User Command: "{text}"
        
        Return ONLY valid JSON. No markdown, no surrounding text.
        Example JSON:
        {{
            "message": "Meeting started",
            "date": "2024-12-30",
            "time": "14:00",
            "repeat": "None",
            "zones": ["Gym"]
        }}
        """
        
        import time
        max_retries = 3
        retry_delay = 2 # seconds

        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                result = json.loads(response.text)
                
                # Post-processing / Sanity Check
                # Only set defaults for message, leave others null if missing to prompt user
                if not result.get("message"): result["message"] = "Announcement"
                
                return result
            except Exception as e:
                if "429" in str(e) or "Resource exhausted" in str(e):
                    if attempt < max_retries - 1:
                        print(f"Rate limit hit. Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        retry_delay *= 2 # Exponential backoff
                        continue
                
                print(f"Error parsing command: {e}")
                return {"error": f"Failed to parse command: {str(e)}"}

# Singleton instance
smart_parser = SmartParser()
