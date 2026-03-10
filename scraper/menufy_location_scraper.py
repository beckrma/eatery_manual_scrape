from playwright.sync_api import sync_playwright
import json
import re
import time
import geocoder


# -----------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------
MENUFY_URL       = "https://www.menufy.com/"
HEADLESS         = False          
MAX_RESTAURANTS  = None      



def get_location() -> str:
    g = geocoder.ip('me')
    if g.ok:
        city  = g.city
        state = g.state
        print(f"Detected location: {city}, {state}")
        return f"{city}, {state}"
    else:
        # Fall back to manual input if detection fails
        print("Could not detect location automatically.")
        return input("Enter your location manually: ").strip()

def clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def strip_result_index(name: str) -> str:
    """Remove leading '1. ', '2. ' numbering that Menufy adds to results."""
    return re.sub(r"^\d+\.\s*", "", name).strip()


def extract_prices(text: str):
    return re.findall(r"\$?\d+(?:\.\d{2})?", text)


# LOCATION PROMPT
def prompt_location() -> str:
    """
    Interactively ask the user for their location.
    Keeps asking until a non-empty string is provided.
    Examples of valid input: 'Irvine, CA'  |  '92614'  |  'Anaheim, California'
    """
    print("\n" + "=" * 55)
    print("       🍽️  Menufy Location-Based Restaurant Scraper")
    print("=" * 55)
    print("Enter your location so we can find nearby restaurants.")
    print("Examples:  'Irvine, CA'  |  '92614'  |  'Anaheim, CA'\n")

    while True:
        location = input("📍 Your location: ").strip()
        if location:
            return location
        print(" Location cannot be empty. Please try again.")


def search_restaurants(page, location: str) -> list:
    """
    Navigate to Menufy, type the user's location into the search box,
    trigger the search, then collect every restaurant anchor in the results.
    """
    print(f"\n Opening Menufy and searching for: '{location}' ...")
    page.goto(MENUFY_URL, wait_until="domcontentloaded", timeout=60_000)
    time.sleep(2)

    # Dismiss any cookie / accept modals
    for sel in ["button:has-text('Accept')", ".btn-close", ".close"]:
        try:
            page.click(sel, timeout=1_200)
        except Exception:
            pass

    # Type into the address search field
    page.fill("#address", location)
    time.sleep(1)

    # Menufy uses a Google Places autocomplete dropdown — press ArrowDown + Enter
    # to select the first suggestion, which normalises the address.
    page.keyboard.press("ArrowDown")
    time.sleep(0.3)
    page.keyboard.press("Enter")
    time.sleep(0.3)

    # Click the Find / Search button
    try:
        page.click("#FindBtn", timeout=2_500)
    except Exception:
        page.keyboard.press("Enter")   # fallback: submit via keyboard

    page.wait_for_timeout(3_500)       # wait for search results to render

    rows = []
    seen_urls = set()
    anchors = page.query_selector_all(
        "a.restaurant, #search-results a.list-group-item.restaurant"
    )

    for a in anchors:
        try:
            href    = a.get_attribute("href") or ""
            lat     = a.get_attribute("data-lat")
            lon     = a.get_attribute("data-lon")
            address = a.get_attribute("data-address") or ""

            title_node = a.query_selector(".list-group-item-heading")
            raw_name   = (
                clean_text(title_node.inner_text()) if title_node
                else clean_text(a.inner_text())
            )
            name = strip_result_index(raw_name)
        except Exception:
            continue

        if not href or not name:
            continue
        if href.startswith("//"):
            href = "https:" + href

        if href in seen_urls:
            continue
        seen_urls.add(href)

        rows.append({
            "name":             name,
            "url":              href,
            "latitude_search":  float(lat) if lat else None,
            "longitude_search": float(lon) if lon else None,
            "address":          address.strip(),
        })

    print(f" Found {len(rows)} restaurant(s) in results.")
    return rows


# RESTAURANT PAGE HELPERS
def get_logo_url(page) -> str:
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
    lat_m = re.search(r"_locationLat\s*=\s*(-?\d+(?:\.\d+)?)", html, re.IGNORECASE)
    lon_m = re.search(r"_locationLng\s*=\s*(-?\d+(?:\.\d+)?)", html, re.IGNORECASE)
    lat = float(lat_m.group(1)) if lat_m else None
    lon = float(lon_m.group(1)) if lon_m else None
    return lat, lon


def extract_phone(page) -> str:
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


def extract_address_from_page(page) -> str:
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


def extract_hours(page) -> str:
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

    # Shadow-root fallback for Menufy's custom web components
    try:
        txt = page.evaluate(
            r"""() => {
                const openHours = document.querySelector('new-menufy-open-hours');
                if (openHours && openHours.shadowRoot) {
                    const text = (openHours.shadowRoot.innerText || '').replace(/\s+/g, ' ').trim();
                    if (text) return text;
                }
                const host = document.querySelector('new-menufy-open-hours-dropdown');
                if (!host || !host.shadowRoot) return '';
                return (host.shadowRoot.innerText || '').replace(/\s+/g, ' ').trim();
            }"""
        )
        if txt and "hours" in txt.lower():
            return txt
    except Exception:
        pass
    return ""


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
    price       = ""
    item_image  = None

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
            m = re.search(r"url\(['\"]?(https?://[^'\"\)]+)", style, re.IGNORECASE)
            if m:
                item_image = m.group(1)
    except Exception:
        pass

    return {"name": name, "price": price, "description": description, "item_image": item_image}


def extract_menu_items_from_shadow(page) -> list:
    """Parse Menufy's new-menufy-menu / new-menufy-category web components."""
    try:
        groups = page.evaluate(
            r"""() => {
                const out = [];
                const menu = document.querySelector('new-menufy-menu');
                if (!menu || !menu.shadowRoot) return out;

                let categoryEls = [];
                const slot = menu.shadowRoot.querySelector('slot[name="slot-id"], slot');
                if (slot) {
                    const assigned = slot.assignedElements ? slot.assignedElements({flatten: true}) : [];
                    for (const el of assigned) {
                        if (!el) continue;
                        if (el.id === 'categories') {
                            categoryEls.push(...el.querySelectorAll('new-menufy-category'));
                        } else {
                            const nested = el.querySelector ? el.querySelector('#categories') : null;
                            if (nested) categoryEls.push(...nested.querySelectorAll('new-menufy-category'));
                        }
                    }
                }
                if (categoryEls.length === 0)
                    categoryEls = Array.from(document.querySelectorAll('new-menufy-category'));
                categoryEls = Array.from(new Set(categoryEls));

                categoryEls.forEach((catEl) => {
                    const sr = catEl.shadowRoot;
                    let nameNode  = catEl.querySelector('#cat-name, .category-name, h2, h3');
                    let descNode  = catEl.querySelector('#menu-category-description, .category-description');
                    let itemCards = catEl.querySelectorAll('#menufy-items-container .item-link, .item-link');

                    if (sr) {
                        const catSlot = sr.querySelector('slot[name="slot-id"], slot');
                        if (catSlot && catSlot.assignedElements) {
                            for (const el of catSlot.assignedElements({flatten: true})) {
                                if (!nameNode)  nameNode  = el.querySelector?.('#cat-name, .category-name, h2, h3') || null;
                                if (!descNode)  descNode  = el.querySelector?.('#menu-category-description, .category-description') || null;
                                if (!itemCards || itemCards.length === 0) {
                                    const found = el.querySelectorAll?.('#menufy-items-container .item-link, .item-link');
                                    if (found && found.length > 0) itemCards = found;
                                }
                            }
                        }
                    }

                    const categoryName        = (nameNode?.textContent || '').trim() || 'Uncategorized';
                    const categoryDescription = (descNode?.textContent  || '').trim();
                    const items = [];
                    const seen  = new Set();

                    itemCards.forEach((card) => {
                        const name = (card.querySelector('.item-name')?.textContent || '').trim();
                        if (!name) return;

                        const description = (card.querySelector('.item-description')?.textContent || '').trim();
                        let price = '';
                        const priceText  = (card.querySelector('.item-price')?.textContent || '').replace(/\s+/g, ' ').trim();
                        const priceMatch = priceText.match(/\$?\d+(?:\.\d{2})?(?:\+)?/);
                        if (priceMatch) price = priceMatch[0];

                        let itemImage = null;
                        const style   = card.querySelector('.item-image-wrapper')?.getAttribute('style') || '';
                        const m       = style.match(/url\(['"]?(https?:\/\/[^'"\)]+)/i);
                        if (m) itemImage = m[1];

                        const key = `${name.toLowerCase()}|${price}`;
                        if (seen.has(key)) return;
                        seen.add(key);
                        items.push({ name, price, description, item_image: itemImage });
                    });

                    if (items.length > 0)
                        out.push({ category: categoryName, category_description: categoryDescription, items });
                });

                return out;
            }"""
        )
        return groups if isinstance(groups, list) else []
    except Exception:
        return []


def extract_menu_items(page) -> list:
    groups = extract_menu_items_from_shadow(page)
    if groups:
        return groups

    # Classic-DOM fallback
    items = []
    seen  = set()
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
        return [{"category": "Uncategorized", "category_description": "", "items": items}]
    return []


def main():
    # 1. Ask the user for their location (keeps prompting until non-empty)
    location = get_location()

    # Build safe filename slug from the location string
    slug = re.sub(r"[^\w]+", "_", location).strip("_").lower()

    restaurant_rows = []
    menu_rows       = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page    = browser.new_page()

        # 2. Search Menufy with the user's location
        results = search_restaurants(page, location)

        # 3. Apply optional cap
        if MAX_RESTAURANTS is not None:
            results = results[:MAX_RESTAURANTS]

        if not results:
            print("\n No restaurants found for that location. Try a different city or ZIP code.")
            browser.close()
            return

        print(f"\n Scraping {len(results)} restaurant(s) \n")

        # 4. Visit each restaurant page and extract details + menu
        for idx, r in enumerate(results, 1):
            print(f"  [{idx}/{len(results)}] {r['name']}")
            try:
                page.goto(r["url"], wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2_500)
            except Exception as e:
                print(f" Could not load page: {e}")
                continue

            # Scroll to trigger lazy-loaded menu content
            for _ in range(5):
                try:
                    page.evaluate("window.scrollBy(0, window.innerHeight);")
                except Exception:
                    pass
                page.wait_for_timeout(700)

            logo_url         = get_logo_url(page)
            lat_page, lon_page = extract_coordinates_from_page(page)
            lat   = lat_page  if lat_page  is not None else r.get("latitude_search")
            lon   = lon_page  if lon_page  is not None else r.get("longitude_search")
            phone = extract_phone(page)
            addr  = extract_address_from_page(page) or r.get("address", "")
            hours = extract_hours(page)

            restaurant_rows.append({
                "restaurant_name": r["name"],
                "restaurant_url":  r["url"],
                "address":         addr,
                "latitude":        lat,
                "longitude":       lon,
                "logo_url":        logo_url,
                "phone":           phone,
                "hours":           hours,
            })

            groups = extract_menu_items(page)
            item_count = 0
            for g in groups:
                item_count += len(g.get("items", []))
                menu_rows.append({
                    "restaurant":           r["name"],
                    "category":             g["category"],
                    "category_description": g["category_description"],
                    "items":                g["items"],
                })
            print(f"       → {len(groups)} categor{'y' if len(groups)==1 else 'ies'}, {item_count} item(s)")

        browser.close()

    # 5. Write results to JSON
    restaurants_file = f"menufy_{slug}_restaurants.json"
    menu_file        = f"menufy_{slug}_menu_items.json"

    with open(restaurants_file, "w", encoding="utf-8") as f:
        json.dump(restaurant_rows, f, ensure_ascii=False, indent=2)
    with open(menu_file, "w", encoding="utf-8") as f:
        json.dump(menu_rows, f, ensure_ascii=False, indent=2)

    print(f"\n Done! Scraped {len(restaurant_rows)} restaurant(s).")
    print(f"    {restaurants_file}")
    print(f"    {menu_file}")


if __name__ == "__main__":
    main()