from playwright.sync_api import sync_playwright
from database.insert_data import EateryDB
import pandas as pd
import re
import json
import time

test_restaurant = [
    {"name": "Nguyen's Kitchen", "url": "https://orange.ordernguyenskitchen.com/"}
]

# Json Storage
rest_info = []

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

# -------------------------------
# MAIN SCRAPER
# -------------------------------
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # headless=True to hide browser
    page = browser.new_page()
    Eatery_DB = EateryDB()
    Eatery_DB.connect() # Connecting to database

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

        # -------- Extract Theme, Logo, and Lattitude/Longitude --------

        logo_meta = page.locator('meta[property="og:image"]')
        logo = logo_meta.get_attribute("content")

        header = page.locator("img.hero-img").get_attribute("src")

        rest_name = page.title()

        rest_desc = page.locator('meta[name="description"]')
        rest_desc = rest_desc.get_attribute("content")

        rest_hours = page.locator("#open-hours-root").first.inner_text()

        extra_hours_info = page.locator(".dropdown-menu.w-full.hours-dropdown").inner_text()

        rest_phone_num = page.locator('[title="Phone"]').inner_text()

        rest_address = address = page.locator('a[target="_blank"][href*="maps.google.com"]').inner_text()

        rest_lat = page.evaluate("window._locationLat")
        rest_lng = page.evaluate("window._locationLng")

        rest_info.append({
            "restaurant": rest_name,
            "logo_img": logo,
            "header_img": header,
            "restaurant_description": rest_desc,
            "restaurant_hours": rest_hours,
            "extra_hours": extra_hours_info,
            "phone_number": rest_phone_num,
            "address": rest_address,
            "latitude_coordinates": rest_lat,
            "longitude_coordinates": rest_lng
        }
        )

        # -------- Extract all Categories and Menu Items --------
        
        categories = page.locator("new-menufy-category")
        category_count = categories.count()

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
                style = item.locator(".item-image-wrapper").evaluate("el => el.style.backgroundImage")
                image_url = None
                if style:
                    match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                    if match:
                        image_url = match.group(1)

                item_list.append({
                    "name": item_name,
                    "price": item_price,
                    "description": item_description,
                    "item_image": image_url
                })
                items_count += 1
        
            Eatery_DB.insert({
                "restaurant": r["name"],
                "category": cat_name,
                "category_description": cat_desc,
                "items": item_list
            })
        
    browser.close()

# -------------------------------
# SAVE RESULTS
# -------------------------------

with open("restaurant_info.json", "w", encoding="utf-8") as i:
    json.dump(rest_info, i, ensure_ascii=False, indent=4 )
print(f"\n✅ Finished scraping {items_count} item(s) from {len(test_restaurant)} restaurant(s)")