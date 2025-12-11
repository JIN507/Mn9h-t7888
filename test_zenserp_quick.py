import requests
import time

ZENSERP_API_KEY = "dc270410-8660-11f0-bccb-fb3d50c822e4"

# Test 1: Simple text search
print("=== Test 1: Simple Text Search ===")
try:
    headers = {'apikey': ZENSERP_API_KEY}
    params = {'q': 'test'}
    
    start = time.time()
    response = requests.get('https://app.zenserp.com/api/v2/search', 
                          headers=headers, params=params, timeout=30)
    elapsed = time.time() - start
    
    print(f"Status: {response.status_code}")
    print(f"Time: {elapsed:.2f}s")
    if response.status_code == 200:
        data = response.json()
        print(f"Response keys: {list(data.keys())}")
    else:
        print(f"Error: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Test 2: Reverse Image Search (Fast Image) ===")
# Test 2: Fast reverse image search with a small, publicly accessible image
fast_image = "https://via.placeholder.com/150"

try:
    headers = {'apikey': ZENSERP_API_KEY}
    params = {
        'image_url': fast_image,
        'search_engine': 'google.com',
        'tbm': 'isch',
        'num': '10'
    }
    
    start = time.time()
    response = requests.get('https://app.zenserp.com/api/v2/search', 
                          headers=headers, params=params, timeout=30)
    elapsed = time.time() - start
    
    print(f"Status: {response.status_code}")
    print(f"Time: {elapsed:.2f}s")
    if response.status_code == 200:
        data = response.json()
        print(f"Response keys: {list(data.keys())}")
        
        # Check for reverse image results
        if 'reverse_image_results' in data:
            reverse = data['reverse_image_results']
            print(f"Reverse image keys: {list(reverse.keys())}")
            if 'organic' in reverse:
                print(f"Found {len(reverse['organic'])} organic results")
        elif 'organic_results' in data:
            print(f"Found {len(data['organic_results'])} organic_results")
        elif 'organic' in data:
            print(f"Found {len(data['organic'])} organic results")
    else:
        print(f"Error: {response.text[:500]}")
except requests.exceptions.Timeout:
    print("TIMEOUT - Request took too long")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Conclusion ===")
print("If Test 1 works but Test 2 times out, the issue is with reverse image search.")
print("If both timeout, there's a network/API connectivity issue.")
