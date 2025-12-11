import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()
key = os.environ.get('ZENSERP_API_KEY')

headers = {'apikey': key}

# Test with a well-known public image
image_url = 'https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/300px-PNG_transparency_demonstration_1.png'

params = {
    'image_url': image_url,
    'gl': 'us',
    'hl': 'en'
}

resp = requests.get('https://app.zenserp.com/api/v2/search', headers=headers, params=params, timeout=60)

data = resp.json()

# Save to file
with open('zenserp_response.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f'Status: {resp.status_code}')
print(f'Response keys: {list(data.keys())}')
print('Full response saved to zenserp_response.json')
