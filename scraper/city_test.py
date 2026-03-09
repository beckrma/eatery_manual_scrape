from playwright.sync_api import sync_playwright
import json
import re
import time


MENUFY_URL = "https://www.menufy.com/"
SEARCH_ADDRESS = "Orange County, CA"
MAX_RESTAURANTS = None


def clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def strip_result_index(name: str) -> str:
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
    # Preferred: maps link anchor containing the rendered address text.
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
            r"""() => {
                const openHours = document.querySelector('new-menufy-open-hours');
                if (openHours && openHours.shadowRoot) {
                    const text = (openHours.shadowRoot.innerText || '').replace(/\s+/g, ' ').trim();
                    if (text) return text;
                }
                const host = document.querySelector('new-menufy-open-hours-dropdown');
                if (!host || !host.shadowRoot) return '';
                const raw = (host.shadowRoot.innerText || '').replace(/\s+/g, ' ').trim();
                return raw;
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


def extract_menu_items_from_shadow(page):
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
                if (categoryEls.length === 0) {
                    categoryEls = Array.from(document.querySelectorAll('new-menufy-category'));
                }
                categoryEls = Array.from(new Set(categoryEls));

                categoryEls.forEach((catEl) => {
                    const sr = catEl.shadowRoot;

                    let categoryNameNode = catEl.querySelector('#cat-name, .category-name, h2, h3');
                    let categoryDescNode = catEl.querySelector('#menu-category-description, .category-description');
                    let itemCards = catEl.querySelectorAll('#menufy-items-container .item-link, .item-link');

                    if (sr) {
                        const catSlot = sr.querySelector('slot[name="slot-id"], slot');
                        if (catSlot && catSlot.assignedElements) {
                            const assigned = catSlot.assignedElements({flatten: true});
                            for (const el of assigned) {
                                if (!categoryNameNode) categoryNameNode = el.querySelector?.('#cat-name, .category-name, h2, h3') || null;
                                if (!categoryDescNode) categoryDescNode = el.querySelector?.('#menu-category-description, .category-description') || null;
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
                        const priceText = (card.querySelector('.item-price')?.textContent || '').replace(/\s+/g, ' ').trim();
                        const priceMatch = priceText.match(/\$?\d+(?:\.\d{2})?(?:\+)?/);
                        if (priceMatch) price = priceMatch[0];

                        let itemImage = null;
                        const style = card.querySelector('.item-image-wrapper')?.getAttribute('style') || '';
                        const m = style.match(/url\(['"]?(https?:\/\/[^'"\)]+)/i);
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


def extract_menu_items(page):
    shadow_groups = extract_menu_items_from_shadow(page)
    if shadow_groups:
        return shadow_groups

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
        return [{"category": "Uncategorized", "category_description": "", "items": items}]
    return []


def search_restaurants(page):
    page.goto(MENUFY_URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(2)

    for sel in ["button:has-text('Accept')", ".btn-close", ".close"]:
        try:
            page.click(sel, timeout=1200)
        except Exception:
            pass

    page.fill("#address", SEARCH_ADDRESS)
    time.sleep(1)
    page.keyboard.press("ArrowDown")
    time.sleep(0.2)
    page.keyboard.press("Enter")
    time.sleep(0.3)

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
                "address": address or "",
            }
        )
    return rows


def choose_restaurants(results):
    if not results:
        return []
    picked = []
    seen = set()
    for r in results:
        if MAX_RESTAURANTS is not None and len(picked) >= MAX_RESTAURANTS:
            break
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        picked.append(r)
    return picked


def main():
    restaurant_rows = []
    menu_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
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
            phone = extract_phone(page)
            address = extract_address_from_page(page) or r.get("address", "")
            hours = extract_hours(page)

            restaurant_rows.append(
                {
                    "restaurant_name": r["name"],
                    "restaurant_url": r["url"],
                    "address": address,
                    "latitude": lat,
                    "longitude": lon,
                    "logo_url": logo_url,
                    "phone": phone,
                    "hours": hours,
                }
            )

            groups = extract_menu_items(page)
            for g in groups:
                menu_rows.append(
                    {
                        "restaurant": r["name"],
                        "category": g["category"],
                        "category_description": g["category_description"],
                        "items": g["items"],
                    }
                )

        browser.close()

    with open("menufy_orange_county_all_restaurants.json", "w", encoding="utf-8") as f:
        json.dump(restaurant_rows, f, ensure_ascii=False, indent=2)
    with open("menufy_orange_county_all_menu_items.json", "w", encoding="utf-8") as f:
        json.dump(menu_rows, f, ensure_ascii=False, indent=2)

    print("Finished.")
    print("Files:")
    print(" - menufy_orange_county_all_restaurants.json")
    print(" - menufy_orange_county_all_menu_items.json")


if __name__ == "__main__":
    main()
