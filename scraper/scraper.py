from playwright.sync_api import sync_playwright
from playwright._impl._errors import TimeoutError
from urllib.parse import urljoin
from database.insert_data import EateryDB
import re
<<<<<<< HEAD
import time
from urllib.parse import urljoin
=======
>>>>>>> 43555050d4a643f77406e013a21199261fc21c4c

def get_city_links(city_locator):
    cities = []
    cities_count = city_locator.count()
    for y in range(cities_count):
        city_href = city_locator.nth(y).get_attribute("href")
        city_title = city_locator.nth(y).inner_text()
        cities.append((city_title, city_href))
    return cities

def get_restaurants(rest_locator):
    restaurants = []
    restaurants_count = rest_locator.count()
    for z in range(restaurants_count):
        restaurant_cuisine_tags = rest_locator.nth(z).locator(".list-group-item-text.cuisines").inner_text()
        restaurant_attribute_tags = rest_locator.nth(z).locator(".list-group-item-text.attributes").inner_text()
        rest_href = rest_locator.nth(z).get_attribute("href")
        restaurants.append((restaurant_cuisine_tags, restaurant_attribute_tags, rest_href))
    return restaurants



def main_scraping(state_list):
    Eatery_DB = EateryDB()
    Eatery_DB.connect() # Connecting to database
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=True to hide browser
        context = browser.new_context()
        main_page = context.new_page()
        for state in state_list:
            city_url = urljoin("https://www.menufy.com/", state)
            main_page.goto(city_url, timeout=60000)
            cities = main_page.locator(".cities a")
            cities_list = get_city_links(cities)
            for city_title, city_link in cities_list:
                city_rest_url = urljoin("https://www.menufy.com/", city_link)
                main_page.goto(city_rest_url, timeout=60000)

<<<<<<< HEAD
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
=======
                restaurants = main_page.locator(".list-group a")
                restaurants_list = get_restaurants(restaurants)
                for restaurant_cuisine_tags, restaurant_attribute_tags, rest_href in restaurants_list:
                    try:
                        main_page.goto(rest_href, timeout=60000)
>>>>>>> 43555050d4a643f77406e013a21199261fc21c4c
                    except Exception as e:
                        print(f"Navigation failed for {rest_href}: {e}")
                        continue
            
                    # -------- Extract Theme, Logo, and Lattitude/Longitude --------
                    try:
                        try:
<<<<<<< HEAD
                            logo_meta = restaurant.locator('meta[property="og:image"]')
=======
                            logo_meta = main_page.locator('meta[property="og:image"]')
>>>>>>> 43555050d4a643f77406e013a21199261fc21c4c
                            logo = logo_meta.get_attribute("content")
                        except TimeoutError as t:
                            logo = "Null"
                        try:
<<<<<<< HEAD
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
=======
                            header = main_page.locator("img.hero-img").get_attribute("src")
                        except TimeoutError as t:
                            header = "Null"

                        rest_name = main_page.title()

                        rest_desc = main_page.locator('meta[name="description"]')
                        rest_desc = rest_desc.get_attribute("content")

                        rest_hours = main_page.locator("#open-hours-root").first.inner_text()

                        extra_hours_info = main_page.locator(".dropdown-menu.w-full.hours-dropdown").inner_text()

                        rest_phone_num = main_page.locator('[title="Phone"]').inner_text()

                        rest_address = main_page.locator('a[target="_blank"][href*="maps.google.com"]').inner_text()

                        rest_lat = main_page.evaluate("window._locationLat")
                        rest_lng = main_page.evaluate("window._locationLng")
                        state_title = main_page.evaluate("""
                            () => {
                                const el = document.querySelector('script[type="application/ld+json"]');
                                const data = JSON.parse(el.textContent);
                                return data.address.addressRegion;
                            }
                            """)
>>>>>>> 43555050d4a643f77406e013a21199261fc21c4c

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
                    
                    categories = main_page.locator("new-menufy-category")
                    category_count = categories.count()

                    for g in range(category_count):
                        try:
                            category = categories.nth(g)
                    
                            # Grab the category name
                            cat_name = category.locator("#cat-name").inner_text()
<<<<<<< HEAD

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
=======
>>>>>>> 43555050d4a643f77406e013a21199261fc21c4c

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
                        
                            Eatery_DB.insert({
                                "restaurant": main_page.title(),
                                "category": cat_name,
                                "category_description": cat_desc,
                                "items": item_list
                            }, 1)
                        except Exception as e:
                            print(f"Menu item scraping failed for {rest_href} : {e}")
                            continue
        browser.close()
    return
