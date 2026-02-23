from playwright.sync_api import sync_playwright
import pandas as pd
import re
import json
import time
import random

test_restaurant = [
    {"name": "Nguyen's Kitchen", "url": "https://orange.ordernguyenskitchen.com/"}
]

all_items = []
items_count = 0
# -------------------------------
# HELPER FUNCTIONS
# -------------------------------
def extract_prices(text):
    """Extract all $ prices from text"""
    return re.findall(r'\$\d+(?:\.\d{2})?', text)

def clean_text(text):
    """Remove extra whitespace and newlines"""
    if not text:
        return ""
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

    for r in test_restaurant:
        print(f"\n🌐 Scraping {r['name']} ...")
        response = page.goto(r["url"])
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

        # Scroll slowly to load dynamic content
        for _ in range(5):
            page.evaluate("window.scrollBy(0, window.innerHeight);")
            time.sleep(1)
        
        if (is_problematic(page, response) == True): # Checks if website is "problematic" (means that no content is available to scrape)
            r_prob["restaurant"].append(r['name'])
            r_prob["url"].append(r['url'])
            pass

            
        # -------- Extract all visible blocks --------
        
        categories = page.locator("new-menufy-category")
        category_count = categories.count()

        menu_json = []

        for i in range(category_count):
            category = categories.nth(i)
    
            # Grab the category name
            cat_name = category.locator("#cat-name").inner_text()

            # Grab the category description (if available)
            cat_desc = category.locator("#menu-category-description").inner_text()
            
            # Grab all items inside this category
            items = category.locator("new-menufy-item-card")
            item_list = []
            for j in range(items.count()):
                item = items.nth(j)
                item_name = item.locator(".item-name").inner_text()
                item_price = item.locator(".item-price span").first.inner_text()
                item_description = item.locator(".item-description").inner_text()
                item_list.append({
                    "name": item_name,
                    "price": item_price,
                    "description": item_description
                })
                items_count += 1
        
            menu_json.append({
                "restaurant": r["name"],
                "category": cat_name,
                "category_description": cat_desc,
                "items": item_list
            })

        all_items.append(menu_json)
        
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
print(f"\n✅ Finished scraping {items_count} item(s) from {len(test_restaurant)} restaurant(s)")