from playwright.sync_api import sync_playwright
import json
import re
import time
from urllib.parse import urljoin


MENUFY_URL = "https://www.menufy.com/"
DEEP_SCRAPE_RESTAURANTS = True

# Keep None for full crawl. Set numeric values for testing.
MAX_STATES = None
MAX_CITIES_PER_STATE = None
MAX_RESTAURANTS_PER_CITY = None

HEADLESS = True
PAUSE_SECONDS = 0.4


def clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def strip_result_index(name: str) -> str:
    return re.sub(r"^\d+\.\s*", "", name).strip()


def extract_prices(text: str):
    return re.findall(r"\$?\d+(?:\.\d{2})?", text)


def normalize_url(base_url: str, href: str):
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return "https:" + href
    return urljoin(base_url, href)


def extract_state_links(page):
    states = []
    seen = set()
    anchors = page.query_selector_all("section#states .state-columns a[href]")
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
            name = clean_text(a.inner_text())
        except Exception:
            continue
        url = normalize_url(MENUFY_URL, href)
        if not url or url in seen or not name:
            continue
        seen.add(url)
        states.append({"state_name": name, "state_url": url})
    return states


def extract_city_links(page, state_name, state_url):
    cities = []
    seen = set()
    anchors = page.query_selector_all("section#search-results .cities a[href], .state-cities .cities a[href]")
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
            name = clean_text(a.inner_text())
        except Exception:
            continue
        url = normalize_url(state_url, href)
        if not url or url in seen or not name:
            continue
        seen.add(url)
        cities.append(
            {
                "state_name": state_name,
                "state_url": state_url,
                "city_name": name,
                "city_url": url,
            }
        )
    return cities


def extract_restaurants(page, state_name, state_url, city_name, city_url):
    restaurants = []
    seen = set()
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
            location_id = a.get_attribute("m-id")
            domain = a.get_attribute("domain")
        except Exception:
            continue

        url = normalize_url(city_url, href)
        if not url or url in seen or not name:
            continue
        seen.add(url)

        restaurants.append(
            {
                "state_name": state_name,
                "city_name": city_name,
                "restaurant_name": name,
                "restaurant_url": url,
                "address": (address or "").strip(),
                "_latitude_search": float(lat) if lat else None,
                "_longitude_search": float(lon) if lon else None,
                "logo_url": "",
                "latitude": None,
                "longitude": None,
                "phone": "",
                "hours": "",
            }
        )
    return restaurants


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
                        return normalize_url(page.url, src)
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


def extract_phone(page):
    try:
        tel = page.query_selector("a[href^='tel:']")
        if tel:
            text = clean_text(tel.inner_text())
            if text:
                return text
            href = tel.get_attribute("href") or ""
            return href.replace("tel:", "").strip()
    except Exception:
        pass
    return ""


def extract_address_from_page(page):
    selectors = [
        "a[href*='maps.google.com'][href*='daddr']",
        "a[href*='google.com/maps'][href*='daddr']",
        "a[href*='maps.google.com']",
    ]
    for sel in selectors:
        try:
            node = page.query_selector(sel)
            if node:
                txt = clean_text(node.inner_text())
                if txt:
                    return txt.strip('" ')
        except Exception:
            pass
    return ""


def extract_hours(page):
    # Hours are rendered in/around custom web components.
    # Try specific selectors first, then fall back to shadow-root extraction.
    selectors = [
        "#open-hours-root",
        "#location-info-hours-dropdown-container",
        "new-menufy-open-hours",
        "new-menufy-open-hours-dropdown",
        "new-menufy-location-info",
    ]
    for sel in selectors:
        try:
            node = page.query_selector(sel)
            if node:
                txt = clean_text(node.inner_text())
                if txt and "hours" in txt.lower():
                    return txt
        except Exception:
            pass

    try:
        txt = page.evaluate(
            """() => {
                const openHours = document.querySelector('new-menufy-open-hours');
                if (openHours && openHours.shadowRoot) {
                    const root = openHours.shadowRoot;
                    const text = (root.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (text) return text;
                }
                const host = document.querySelector('new-menufy-open-hours-dropdown');
                if (!host || !host.shadowRoot) return '';
                const raw = (host.shadowRoot.innerText || '').replace(/\\s+/g, ' ').trim();
                return raw;
            }"""
        )
        if txt and "hours" in txt.lower():
            return txt
    except Exception:
        pass

    return ""


def extract_menu_items_from_shadow(page):
    # Parse menu categories/items from custom elements:
    # new-menufy-menu (shadow root) -> slot content -> #categories -> new-menufy-category.
    # Fallback to document-level new-menufy-category if slot traversal differs.
    try:
        groups = page.evaluate(
            """() => {
                const out = [];
                const menu = document.querySelector('new-menufy-menu');
                if (!menu || !menu.shadowRoot) return out;

                let categoryEls = [];

                // Preferred path: slotted content inside new-menufy-menu shadow root.
                const slot = menu.shadowRoot.querySelector('slot[name="slot-id"], slot');
                if (slot) {
                    const assigned = slot.assignedElements ? slot.assignedElements({flatten: true}) : [];
                    for (const el of assigned) {
                        if (!el) continue;
                        if (el.id === 'categories') {
                            categoryEls.push(...el.querySelectorAll('new-menufy-category'));
                        } else {
                            const nested = el.querySelector ? el.querySelector('#categories') : null;
                            if (nested) {
                                categoryEls.push(...nested.querySelectorAll('new-menufy-category'));
                            }
                        }
                    }
                }

                // Fallback: if slot traversal yields nothing, read document-level categories.
                if (categoryEls.length === 0) {
                    categoryEls = Array.from(document.querySelectorAll('new-menufy-category'));
                }

                // De-duplicate category elements.
                categoryEls = Array.from(new Set(categoryEls));
                categoryEls.forEach((catEl) => {
                    const sr = catEl.shadowRoot;

                    // In many Menufy pages, category header/items live in light DOM
                    // and are slotted into the shadow tree.
                    let categoryNameNode = catEl.querySelector('#cat-name, .category-name, h2, h3');
                    let categoryDescNode = catEl.querySelector('#menu-category-description, .category-description');
                    let itemCards = catEl.querySelectorAll('#menufy-items-container .item-link, .item-link');

                    if (sr) {
                        const slot = sr.querySelector('slot[name="slot-id"], slot');
                        if (slot && slot.assignedElements) {
                            const assigned = slot.assignedElements({flatten: true});
                            for (const el of assigned) {
                                if (!categoryNameNode) {
                                    categoryNameNode = el.querySelector?.('#cat-name, .category-name, h2, h3') || null;
                                }
                                if (!categoryDescNode) {
                                    categoryDescNode = el.querySelector?.('#menu-category-description, .category-description') || null;
                                }
                                if (!itemCards || itemCards.length === 0) {
                                    const found = el.querySelectorAll?.('#menufy-items-container .item-link, .item-link');
                                    if (found && found.length > 0) itemCards = found;
                                }
                            }
                        }
                    }

                    const categoryName = (categoryNameNode?.textContent || '').trim() || 'Uncategorized';
                    const categoryDescription = (categoryDescNode?.textContent || '').trim();

                    const items = [];
                    const seen = new Set();

                    itemCards.forEach((card) => {
                        const name = (card.querySelector('.item-name')?.textContent || '').trim();
                        if (!name) return;

                        const description = (card.querySelector('.item-description')?.textContent || '').trim();
                        let price = '';
                        const priceText = (card.querySelector('.item-price')?.textContent || '').replace(/\\s+/g, ' ').trim();
                        const priceMatch = priceText.match(/\\$?\\d+(?:\\.\\d{2})?(?:\\+)?/);
                        if (priceMatch) price = priceMatch[0];

                        let itemImage = null;
                        const style = card.querySelector('.item-image-wrapper')?.getAttribute('style') || '';
                        const m = style.match(/url\\(['"]?(https?:\\/\\/[^'"\\)]+)/i);
                        if (m) itemImage = m[1];

                        const key = `${name.toLowerCase()}|${price}`;
                        if (seen.has(key)) return;
                        seen.add(key);

                        items.push({
                            name,
                            price,
                            description,
                            item_image: itemImage,
                        });
                    });

                    if (items.length > 0) {
                        out.push({
                            category: categoryName,
                            category_description: categoryDescription,
                            items,
                        });
                    }
                });

                return out;
            }"""
        )
        return groups if isinstance(groups, list) else []
    except Exception:
        return []


def parse_item_card(card):
    try:
        name_node = card.query_selector(".item-name")
        if not name_node:
            return None
        name = clean_text(name_node.inner_text())
    except Exception:
        return None
    if not name:
        return None

    description = ""
    price = ""
    item_image = None

    try:
        desc_node = card.query_selector(".item-description")
        if desc_node:
            description = clean_text(desc_node.inner_text())
    except Exception:
        pass

    try:
        price_node = card.query_selector(".item-price")
        if price_node:
            prices = extract_prices(clean_text(price_node.inner_text()))
            if prices:
                price = prices[0]
    except Exception:
        pass

    try:
        img_node = card.query_selector(".item-image-wrapper")
        if img_node:
            style = img_node.get_attribute("style") or ""
            m = re.search(r"url\(['\"]?(https?://[^'\"\)]+)", style, flags=re.IGNORECASE)
            if m:
                item_image = m.group(1)
    except Exception:
        pass

    return {
        "name": name,
        "price": price,
        "description": description,
        "item_image": item_image,
    }


def extract_menu_items(page):
    # Prefer shadow-root parsing for new Menufy components.
    shadow_groups = extract_menu_items_from_shadow(page)
    if shadow_groups:
        return shadow_groups

    groups = []

    category_blocks = page.query_selector_all(".category")
    if category_blocks:
        for cat in category_blocks:
            category_name = "Uncategorized"
            category_description = ""

            try:
                name_node = (
                    cat.query_selector(".category-name")
                    or cat.query_selector(".category-header")
                    or cat.query_selector("h2")
                    or cat.query_selector("h3")
                )
                if name_node:
                    txt = clean_text(name_node.inner_text())
                    if txt:
                        category_name = txt
            except Exception:
                pass

            try:
                desc_node = cat.query_selector(".category-description") or cat.query_selector(".category-desc")
                if desc_node:
                    category_description = clean_text(desc_node.inner_text())
            except Exception:
                pass

            items = []
            seen = set()
            for card in cat.query_selector_all(".item-link"):
                parsed = parse_item_card(card)
                if not parsed:
                    continue
                key = (parsed["name"].lower(), parsed["price"])
                if key in seen:
                    continue
                seen.add(key)
                items.append(parsed)

            if items:
                groups.append(
                    {
                        "category": category_name,
                        "category_description": category_description,
                        "items": items,
                    }
                )

    if groups:
        return groups

    # Fallback when category wrappers are not present.
    items = []
    seen = set()
    for card in page.query_selector_all(".item-link"):
        parsed = parse_item_card(card)
        if not parsed:
            continue
        key = (parsed["name"].lower(), parsed["price"])
        if key in seen:
            continue
        seen.add(key)
        items.append(parsed)

    if items:
        groups.append(
            {
                "category": "Uncategorized",
                "category_description": "",
                "items": items,
            }
        )
    return groups


def maybe_click_accept(page):
    for sel in ["button:has-text('Accept')", ".btn-close", ".close"]:
        try:
            page.click(sel, timeout=800)
        except Exception:
            pass


def main():
    restaurant_rows = []
    menu_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()

        print(f"Opening {MENUFY_URL}")
        page.goto(MENUFY_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        maybe_click_accept(page)

        states = extract_state_links(page)
        if MAX_STATES is not None:
            states = states[:MAX_STATES]

        print(f"Found {len(states)} states.")

        for state in states:
            print(f"State: {state['state_name']} -> {state['state_url']}")
            try:
                page.goto(state["state_url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1000)
            except Exception:
                continue

            cities = extract_city_links(page, state["state_name"], state["state_url"])
            if MAX_CITIES_PER_STATE is not None:
                cities = cities[:MAX_CITIES_PER_STATE]
            print(f"  Cities found: {len(cities)}")

            for city in cities:
                try:
                    page.goto(city["city_url"], wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1200)
                except Exception:
                    continue

                restaurants = extract_restaurants(
                    page,
                    city["state_name"],
                    city["state_url"],
                    city["city_name"],
                    city["city_url"],
                )
                if MAX_RESTAURANTS_PER_CITY is not None:
                    restaurants = restaurants[:MAX_RESTAURANTS_PER_CITY]

                restaurant_rows.extend(restaurants)
                print(f"    {city['city_name']}: {len(restaurants)} restaurants")
                time.sleep(PAUSE_SECONDS)

        # De-duplicate restaurants by URL.
        dedup = {}
        for r in restaurant_rows:
            dedup[r["restaurant_url"]] = r
        restaurant_rows = list(dedup.values())
        print(f"Unique restaurants discovered: {len(restaurant_rows)}")

        if DEEP_SCRAPE_RESTAURANTS:
            print("Deep scrape enabled: visiting each restaurant page.")
            for r in restaurant_rows:
                try:
                    page.goto(r["restaurant_url"], wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1800)
                except Exception:
                    continue

                for _ in range(4):
                    try:
                        page.evaluate("window.scrollBy(0, window.innerHeight);")
                    except Exception:
                        pass
                    page.wait_for_timeout(500)

                logo_url = get_logo_url(page)
                lat_page, lon_page = extract_coordinates_from_page(page)
                lat = lat_page if lat_page is not None else r.get("_latitude_search")
                lon = lon_page if lon_page is not None else r.get("_longitude_search")
                phone = extract_phone(page)
                address = extract_address_from_page(page) or r.get("address", "")
                hours = extract_hours(page)

                r["logo_url"] = logo_url
                r["latitude"] = lat
                r["longitude"] = lon
                r["phone"] = phone
                r["address"] = address
                r["hours"] = hours

                menu_groups = extract_menu_items(page)
                for g in menu_groups:
                    menu_rows.append(
                        {
                            "restaurant": r["restaurant_name"],
                            "category": g["category"],
                            "category_description": g["category_description"],
                            "items": g["items"],
                        }
                    )
                time.sleep(PAUSE_SECONDS)

        browser.close()

    # Remove internal fields before writing final JSON.
    for r in restaurant_rows:
        r.pop("_latitude_search", None)
        r.pop("_longitude_search", None)

    with open("menufy_all_restaurants.json", "w", encoding="utf-8") as f:
        json.dump(restaurant_rows, f, ensure_ascii=False, indent=2)

    with open("menufy_all_menu_items.json", "w", encoding="utf-8") as f:
        json.dump(menu_rows, f, ensure_ascii=False, indent=2)

    print("Finished full site crawl.")
    print("Files:")
    print(" - menufy_all_restaurants.json")
    print(" - menufy_all_menu_items.json")


if __name__ == "__main__":
    main()
