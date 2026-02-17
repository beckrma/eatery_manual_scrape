from playwright.sync_api import sync_playwright
import pandas as pd
import re
import json
import time
import random

# -------------------------------
# RESTAURANTS WITH URL
# -------------------------------
restaurants = [
    {"name": "Blaze Pizza", "url": "https://www.blazepizza.com/menu"},
    {"name": "The Taco Stand", "url": "https://letstaco.com/menu/"},
    {"name": "Nguyen’s Kitchen", "url": "https://www.nguyenskitchen.com/menu/"},
    {"name": "Blk Dot Coffee", "url": "https://www.blkdotcoffee.com/?location=L8Z4FQ9TEQN51#ZBK7AVLHCGCNKDAD5WGG2HY4"},
    {"name": "7 Leaves Coffee", "url": "https://7leavescafe.com/menu/"},
    {"name": "Acai Republic", "url": "https://www.acairepublic.com/our-menu"}
]

all_items = []
# -------------------------------
# HELPER FUNCTIONS
# -------------------------------
def extract_prices(text):
    """Extract all $ prices from text"""
    return re.findall(r'\$\d+(?:\.\d{2})?', text)

def clean_text(text):
    """Remove extra whitespace and newlines"""
    return " ".join(text.strip().split())

skip_keywords = [
    "home", "about", "locations", "menu", "rewards", "franchising",
    "gift", "login", "sign", "order", "checkout",
    "career", "privacy", "cookie", "terms", "subscribe", "newsletter", "Access Denied", "Attention Required", "Verify you are human", "Just a moment...."
]

def is_valid(text):
    text = text.lower()
    if len(text.strip()) < 5:
        return False
    if any(k in text for k in skip_keywords):
        return False
    return True

def is_problematic(page, response):
    if page.title() in skip_keywords:
        return True
    if page.locator("iframe[src*='captcha']").count() > 0: # Detects captchas
        return True
    if response.status == "403" or response.status == "429" or response.status == "503": # Detects response issues
        return True
    html = page.content()
    if "cloudflare" in html.lower(): # Checks if on cloudflare verification
        return True
    return False

r_prob = {"restaurant": [], "url": []}
# -------------------------------
# MAIN SCRAPER
# -------------------------------
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # headless=True to hide browser
    page = browser.new_page()

    for r in restaurants:
        print(f"\n🌐 Scraping {r['name']} ...")
        page.goto(r["url"])
        time.sleep(2)

        # -------- Agentic interactions --------
        # Try to check consent/accept modals
        try:
            page.check("input[type='checkbox']", timeout=2000)
        except:
            pass
        try:
            page.click("button.accept, button#accept, button.cookie-consent", timeout=2000)
        except:
            pass
        
        # Click Menu Buttons
        try:
            link = page.get_attribute("text=menu", "href")
            response = page.goto(link)
            time.sleep(random.uniform(2, 5))
        except:
            pass

        # Click Pickup or Delivery Buttons
        try:
            link = page.get_attribute("text=pickup", "href")
            response = page.goto(link)
            time.sleep(random.uniform(2, 5))
        except:
            pass

        # Scroll slowly to load dynamic content
        for _ in range(5):
            page.evaluate("window.scrollBy(0, window.innerHeight);")
            time.sleep(1)
        
        if (is_problematic(page, response) == True): # Checks if website is "problematic" (means that no content is available to scrape)
            r_prob["restaurant"].append(r['name'])
            r_prob["url"].append(r['url'])
            pass

            
        # -------- Extract all visible blocks --------
        blocks = page.query_selector_all("div, li, section")

        seen = set()  # deduplicate
        for b in blocks:
            try:
                text = clean_text(b.inner_text())
            except:
                continue
            if not is_valid(text):
                continue

            # Extract name and prices
            prices = extract_prices(text)
            item_name = re.sub(r'\$?\d+(?:\.\d{2})?', '', text).strip()

            if (r["name"], item_name) in seen:
                continue
            seen.add((r["name"], item_name))

            # Assign section/description if multiple lines
            description = ""
            lines = text.split("\n")
            if len(lines) > 1:
                description = lines[0]

            all_items.append({
                "restaurant": r["name"],
                "item": item_name,
                "price": ", ".join(prices),
                "description": description
            })

    browser.close()

# -------------------------------
# SAVE RESULTS
# -------------------------------
df = pd.DataFrame(all_items)
prob_df = pd.DataFrame(r_prob)
prob_df.to_csv("menus_prob.csv", index=False)
df.to_csv("menus_agentic.csv", index=False)
with open("menus_agentic.json", "w", encoding="utf-8") as f:
    json.dump(all_items, f, ensure_ascii=False, indent=4)

print(f"\n✅ Finished scraping {len(all_items)} items from {len(restaurants)} restaurants")