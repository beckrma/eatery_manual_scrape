from playwright.sync_api import sync_playwright
from database.insert_data import EateryDB
import re
import time
from urllib.parse import urljoin

test_restaurant = [
    {"name": "Menufy", "url": "https://www.menufy.com/"}
]

items_count = 0


# -------------------------------
# MAIN SCRAPER
# -------------------------------
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # headless=True to hide browser

    context = browser.new_context()
    page = context.new_page()
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

        # -------- Iterating Through States --------
        states = page.locator(".state-columns a")
        state_count = states.count()
    
        for i in range(state_count):
            state_href = states.nth(i).get_attribute("href")
            state_title = states.nth(i).inner_text()

            city_page = context.new_page()
            city_url = urljoin("https://www.menufy.com/", state_href)
            city_page.goto(city_url, timeout=60000)

            cities = city_page.locator(".cities a")
            cities_count = cities.count()
            for y in range(cities_count):
                city_href = cities.nth(y).get_attribute("href")
                city_title = cities.nth(y).inner_text()

                city_rest = context.new_page()
                city_rest_url = urljoin("https://www.menufy.com/", city_href)
                city_rest.goto(city_rest_url, timeout=60000)

                restaurants = city_rest.locator(".list-group a")
                restaurants_count = restaurants.count()
                for z in range(restaurants_count):

                    restaurant_cuisine_tags = restaurants.nth(z).locator(".list-group-item-text.cuisines").inner_text()
                    restaurant_attribute_tags = restaurants.nth(z).locator(".list-group-item-text.attributes").inner_text()

                    rest_href = restaurants.nth(z).get_attribute("href")
                    restaurant = context.new_page()
                    try:
                        restaurant.goto(rest_href, timeout=60000)
                    except Exception as e:
                        print(f"Navigation failed for {rest_href}: {e}")
                        continue
                    for _ in range(5):
                        restaurant.evaluate("window.scrollBy(0, window.innerHeight);")
                        time.sleep(1)

            
                    # -------- Extract Theme, Logo, and Lattitude/Longitude --------
                    try:
                        try:
                            logo_meta = restaurant.locator('meta[property="og:image"]')
                            logo = logo_meta.get_attribute("content")
                        except TimeoutError as t:
                            logo = "Null"
                        try:
                            header = restaurant.locator("img.hero-img").get_attribute("src")
                        except TimeoutError as t:
                            header = "Null"

                        rest_name = restaurant.title()

                        rest_desc = restaurant.locator('meta[name="description"]')
                        rest_desc = rest_desc.get_attribute("content")

                        rest_hours = restaurant.locator("#open-hours-root").first.inner_text()

                        extra_hours_info = restaurant.locator(".dropdown-menu.w-full.hours-dropdown").inner_text()

                        rest_phone_num = restaurant.locator('[title="Phone"]').inner_text()

                        rest_address = address = restaurant.locator('a[target="_blank"][href*="maps.google.com"]').inner_text()

                        rest_lat = restaurant.evaluate("window._locationLat")
                        rest_lng = restaurant.evaluate("window._locationLng")

                        Eatery_DB.insert({
                            "restaurant": rest_name,
                            "logo_img": logo,
                            "header_img": header,
                            "restaurant_description": rest_desc,
                            "restaurant_hours": rest_hours,
                            "extra_hours": extra_hours_info,
                            "phone_number": rest_phone_num,
                            "address": rest_address,
                            "latitude_coordinates": rest_lat,
                            "longitude_coordinates": rest_lng,
                            "state": state_title,
                            "city": city_title,
                            "cuisine_tags": restaurant_cuisine_tags,
                            "attribute_tags": restaurant_attribute_tags
                        }, 2)
                    except Exception as e:
                        print(f"Restaurant information scraping failed for {rest_href}: {e}")
                        continue

                    # -------- Extract all Categories and Menu Items --------
                    
                    categories = restaurant.locator("new-menufy-category")
                    category_count = categories.count()

                    for g in range(category_count):
                        try:
                            category = categories.nth(g)
                    
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
                                "restaurant": restaurant.title(),
                                "category": cat_name,
                                "category_description": cat_desc,
                                "items": item_list
                            }, 1)
                        except Exception as e:
                            print(f"Menu item scraping failed for {rest_href} : {e}")
                            continue

                    restaurant.close()
                city_rest.close()
            city_page.close()
        states.close()
                
        
    browser.close()

print(f"\n✅ Finished scraping {items_count} item(s) from {len(test_restaurant)} restaurant(s)")