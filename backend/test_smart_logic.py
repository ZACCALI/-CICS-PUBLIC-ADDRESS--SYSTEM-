
from api.smart_parser import smart_parser
import json

test_cases = [
    "Announce Fire Drill tomorrow at 9am",
    "Tell the library that closing time is in 10 minutes",
    "Flag ceremony every monday for everyone",
    "Before: Sanitize",
    "Earthquake",
    "Lockdown",
    "Grades due next friday at 3pm",
    "Enrollment starts on Jan 5th",
    "Practice in 20 minutes",
    "Clearance",
    "Frie Drill",
    "Please anounce eartquake",
    "Go to the Libary",
    "Flag cermony",
    "Unifrm"
]

print("--- TESTING SMART PARSER (NO AI) ---")
for text in test_cases:
    print(f"\nInput: '{text}'")
    result = smart_parser.parse_command(text)
    print("Output:", json.dumps(result, indent=2))

print("\n--- TEST COMPLETE ---")
