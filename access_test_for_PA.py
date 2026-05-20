#Imports
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# Suppresses the SSL warning that appears when verify=False is used

# 2. Configuration
URL = "https://platform.prosapient.com/client/projects/ef3ae048-29ac-46c6-9b36-66a2a3a9fd60/experts/c2ce1c89-6914-44ea-97fd-0f86fc484d4b?ga=0q13m5I4yLRCxbIbSdEz-Ohz2bQKsG7i7ixmKnxgVGtcjVFLLCHBZaUNkUHhA3Lm&utm_campaign=Expert_list_external_link&utm_medium=link&utm_source=bio_email"
# Stores the target URL as a constant for easy reuse/modification

HEADERS = {"User-Agent": "Mozilla/5.0"}
# Mimics a real browser request; some sites block Python's default user-agent


# Cell 3 — Accessibility check
def check_accessibility(url: str) -> bool:
    try:
        response = requests.head(url, headers=HEADERS, timeout=10, verify=False)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"Connection error: {e}")
        return False
    

# Cell 4 — Fetch page
def fetch_page(url: str) -> str | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch page: {e}")
        return None
    
    

# 5 — Main execution
if check_accessibility(URL):
    print("SUCCESS: Site is accessible")
    html = fetch_page(URL)
    if html:
        print(f"SUCCESS: Page fetched successfully ({len(html):,} characters)")
        print("\n--- First 500 characters of HTML ---")
        print(html[:500])
else:
    print("FAILED: Site is not accessible — check the URL or your network connection")
    
    
    