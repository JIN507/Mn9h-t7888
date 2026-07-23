
import requests
import os
import dateparser
from datetime import datetime
import json
import sys

# Windows console encoding fix
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

ZENSERP_API_KEY = os.environ.get("ZENSERP_API_KEY")

def test_zenserp_sorting():
    headers = {'apikey': ZENSERP_API_KEY}
    # Search for something that yields dates
    params = {
        'q': 'Palestine news', 
        'num': 10, 
        'gl': 'sa',
        'hl': 'ar'
    }
    
    print(f"[*] Querying Zenserp with key: {ZENSERP_API_KEY[:5]}...")
    try:
        resp = requests.get('https://app.zenserp.com/api/v2/search', headers=headers, params=params, timeout=60)
        print(f"[*] Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(resp.text)
            return

        zenserp_data = resp.json()
        items_to_process = []

        def parse_item(item):
            title = item.get('title', 'No Title')
            snippet = item.get('description') or item.get('snippet') or item.get('title')
            date_str = item.get('date')
            
            # Simple date extraction fallback if date is missing
            if not date_str and snippet:
                import re
                # Regex candidates
                date_candidates = []
                
                # 1. Standard Date: "Oct 25, 2023" or "2023-10-25"
                match_std = re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b|\b\d{4}-\d{2}-\d{2}\b', snippet)
                if match_std: date_candidates.append(match_std.group(0))

                # 2. Relative English: "2 hours ago", "5 mins ago"
                match_rel_en = re.search(r'\b\d+\s+(?:sec|min|hour|day|week|month|year)s?\s+ago\b', snippet, re.IGNORECASE)
                if match_rel_en: date_candidates.append(match_rel_en.group(0))

                # 3. Relative Arabic: "منذ 3 ساعات", "منذ يومين"
                match_rel_ar = re.search(r'\bمنذ\s+(?:\d+|يومين|ساعتين)\s+(?:ثواني|ثانية|دقائق|دقيقة|ساعات|ساعة|أيام|يوم|أسابيع|أسبوع|أشهر|شهر|سنوات|سنة)\b', snippet)
                if match_rel_ar: date_candidates.append(match_rel_ar.group(0))

                if date_candidates:
                    date_str = date_candidates[0] # Take first match

            timestamp = None
            if date_str:
                # Try parsing with and without language hints
                dt = dateparser.parse(date_str)
                if dt: timestamp = dt.isoformat()
            
            return {
                'title': title,
                'date_text': date_str,
                'timestamp': timestamp,
                'snippet': snippet[:30] + '...' if snippet else ''
            }

        # Harvest organic results
        if 'organic' in zenserp_data:
            print(f"[*] First raw item: {json.dumps(zenserp_data['organic'][0], indent=2)}")
            for item in zenserp_data['organic']:
                items_to_process.append(parse_item(item))

        print(f"\n[*] Found {len(items_to_process)} items.")
        
        # Sort Logic from app.py
        # unique_items.sort(key=lambda x: (x['timestamp'] is None, x['timestamp']))
        
        items_to_process.sort(key=lambda x: (x['timestamp'] is None, x['timestamp']))

        print("\n[*] Sorted Results (Oldest First?):")
        for item in items_to_process:
            print(f"Date: {item['date_text']} | TS: {item['timestamp']} | Title: {item['title'][:50]}")

    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    test_zenserp_sorting()
