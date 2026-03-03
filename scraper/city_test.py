from playwright.sync_api import sync_playwright
import pandas as pd
import json
import re
import time


MENUFY_URL = "https://www.menufy.com/"
SEARCH_ADDRESS = "Orange County, CA"
MAX_RESTAURANTS = 7


def clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def strip_result_index(name: str) -> str:
    # Example: "1. Nguyen's Kitchen" -> "Nguyen's Kitchen"
    return re.sub(r"^\d+\.\s*", "", name).strip()


def extract_prices(text: str):
    return re.findall(r"\$?\d+(?:\.\d{2})?", text)


def get_logo_url(page):
    selectors = [
        "meta[property='og:image']",
        "meta[name='twitter:image']",
        "img[alt*='logo' i]",
        "header img",
        ".navbar-brand img",
    ]
    for sel in selectors:
        try:
            if sel.startswith("meta"):
                node = page.query_selector(sel)
                if node:
                    content = node.get_attribute("content")
                    if content and content.startswith("http"):
                        return content
            else:
                node = page.query_selector(sel)
                if node:
                    src = node.get_attribute("src")
                    if src:
                        return src
        except Exception:
            continue
    return ""


def extract_coordinates_from_page(page):
    html = page.content()
    lat_match = re.search(r"_locationLat\s*=\s*(-?\d+(?:\.\d+)?)", html, flags=re.IGNORECASE)
    lon_match = re.search(r"_locationLng\s*=\s*(-?\d+(?:\.\d+)?)", html, flags=re.IGNORECASE)
    lat = float(lat_match.group(1)) if lat_match else None
    lon = float(lon_match.group(1)) if lon_match else None
    return lat, lon


def extract_menu_items(page):
    rows = []
    seen = set()
    cards = page.query_selector_all(".item-link")
    for c in cards:
        try:
            name_node = c.query_selector(".item-name")
            if not name_node:
                continue
            name = clean_text(name_node.inner_text())
        except Exception:
            continue
        if not name:
            continue

        description = ""
        price = ""
        image_url = ""

        try:
            desc_node = c.query_selector(".item-description")
            if desc_node:
                description = clean_text(desc_node.inner_text())
        except Exception:
            pass

        try:
            price_node = c.query_selector(".item-price")
            if price_node:
                prices = extract_prices(clean_text(price_node.inner_text()))
                if prices:
                    price = prices[0]
        except Exception:
            pass

        try:
            img_node = c.query_selector(".item-image-wrapper")
            if img_node:
                style = img_node.get_attribute("style") or ""
                m = re.search(r"url\(['\"]?(https?://[^'\"\)]+)", style, flags=re.IGNORECASE)
                if m:
                    image_url = m.group(1)
        except Exception:
            pass

        key = (name.lower(), price)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "item_name": name,
                "description": description,
                "price": price,
                "item_image_url": image_url,
            }
        )
    return rows


def search_restaurants(page):
    page.goto(MENUFY_URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(2)

    for sel in ["button:has-text('Accept')", ".btn-close", ".close"]:
        try:
            page.click(sel, timeout=1200)
        except Exception:
            pass

    # Address search bar from your HTML: <input id="address" ...>
    page.fill("#address", SEARCH_ADDRESS)
    time.sleep(1)

    # Try selecting Google Places suggestion to make autocomplete.getPlace() valid.
    page.keyboard.press("ArrowDown")
    time.sleep(0.2)
    page.keyboard.press("Enter")
    time.sleep(0.3)

    # Submit search
    try:
        page.click("#FindBtn", timeout=2500)
    except Exception:
        page.keyboard.press("Enter")

    page.wait_for_timeout(3500)

    rows = []
    anchors = page.query_selector_all("a.restaurant, #search-results a.list-group-item.restaurant")
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
            title_node = a.query_selector(".list-group-item-heading")
            raw_name = clean_text(title_node.inner_text()) if title_node else clean_text(a.inner_text())
            name = strip_result_index(raw_name)
            lat = a.get_attribute("data-lat")
            lon = a.get_attribute("data-lon")
            address = a.get_attribute("data-address")
        except Exception:
            continue
        if not href or not name:
            continue
        if href.startswith("//"):
            href = "https:" + href
        rows.append(
            {
                "name": name,
                "url": href,
                "latitude_search": float(lat) if lat else None,
                "longitude_search": float(lon) if lon else None,
                "address_search": address or "",
            }
        )
    return rows


def choose_restaurants(results):
    if not results:
        return []

    picked = []
    used_urls = set()
    # Select first N unique restaurants from search results.
    for r in results:
        if len(picked) >= MAX_RESTAURANTS:
            break
        if r["url"] in used_urls:
            continue
        picked.append(r)
        used_urls.add(r["url"])

    return picked


def main():
    restaurant_rows = []
    menu_rows = []
    image_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("Searching Menufy using address input...")
        results = search_restaurants(page)
        selected = choose_restaurants(results)
        print(f"Selected {len(selected)} restaurant(s) from search results.")

        for r in selected:
            print(f"Scraping: {r['name']} -> {r['url']}")
            try:
                page.goto(r["url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)
            except Exception:
                continue

            for _ in range(5):
                try:
                    page.evaluate("window.scrollBy(0, window.innerHeight);")
                except Exception:
                    pass
                page.wait_for_timeout(700)

            logo_url = get_logo_url(page)
            lat_page, lon_page = extract_coordinates_from_page(page)
            lat = lat_page if lat_page is not None else r.get("latitude_search")
            lon = lon_page if lon_page is not None else r.get("longitude_search")

            restaurant_rows.append(
                {
                    "restaurant_name": r["name"],
                    "restaurant_url": r["url"],
                    "address_search": r.get("address_search", ""),
                    "latitude": lat,
                    "longitude": lon,
                    "logo_url": logo_url,
                }
            )

            if logo_url:
                image_rows.append(
                    {
                        "restaurant_name": r["name"],
                        "restaurant_url": r["url"],
                        "type": "logo",
                        "image_url": logo_url,
                        "latitude": lat,
                        "longitude": lon,
                    }
                )

            items = extract_menu_items(page)
            item_images_seen = set()
            for it in items:
                menu_rows.append(
                    {
                        "restaurant_name": r["name"],
                        "restaurant_url": r["url"],
                        "latitude": lat,
                        "longitude": lon,
                        "item_name": it["item_name"],
                        "description": it["description"],
                        "price": it["price"],
                        "item_image_url": it["item_image_url"],
                    }
                )

                if it["item_image_url"] and it["item_image_url"] not in item_images_seen:
                    item_images_seen.add(it["item_image_url"])
                    image_rows.append(
                        {
                            "restaurant_name": r["name"],
                            "restaurant_url": r["url"],
                            "type": "item_image",
                            "image_url": it["item_image_url"],
                            "latitude": lat,
                            "longitude": lon,
                        }
                    )

        browser.close()

    pd.DataFrame(restaurant_rows).to_csv("menufy_seven_restaurants.csv", index=False)
    pd.DataFrame(menu_rows).to_csv("menufy_seven_menu_items.csv", index=False)
    pd.DataFrame(image_rows).to_csv("menufy_seven_images.csv", index=False)

    with open("menufy_seven_restaurants.json", "w", encoding="utf-8") as f:
        json.dump(restaurant_rows, f, ensure_ascii=False, indent=2)
    with open("menufy_seven_menu_items.json", "w", encoding="utf-8") as f:
        json.dump(menu_rows, f, ensure_ascii=False, indent=2)
    with open("menufy_seven_images.json", "w", encoding="utf-8") as f:
        json.dump(image_rows, f, ensure_ascii=False, indent=2)

    print("Finished.")
    print("Files:")
    print(" - menufy_seven_restaurants.csv/json")
    print(" - menufy_seven_menu_items.csv/json")
    print(" - menufy_seven_images.csv/json")


if __name__ == "__main__":
    main()
