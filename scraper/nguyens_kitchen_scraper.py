from playwright.sync_api import sync_playwright
import pandas as pd
import json
import re
import time
import os
import requests
from urllib.parse import urlparse


TARGET = {
    "name": "Nguyen's Kitchen",
    "url": "https://orange.ordernguyenskitchen.com/",
}

DOWNLOAD_IMAGES = True
IMAGE_DIR = "nguyens_kitchen_images"


def clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def extract_prices(text: str):
    return re.findall(r"\$?\d+(?:\.\d{2})?", text)


def safe_filename(url: str, fallback: str):
    try:
        path = urlparse(url).path
        name = os.path.basename(path).strip()
        if name:
            return name
    except Exception:
        pass
    return fallback


def download_image(url: str, folder: str, fallback_name: str):
    if not url:
        return ""
    os.makedirs(folder, exist_ok=True)
    fname = safe_filename(url, fallback_name)
    out = os.path.join(folder, fname)
    if os.path.exists(out):
        return out
    try:
        r = requests.get(url, timeout=20)
        if r.status_code >= 400:
            return ""
        with open(out, "wb") as f:
            f.write(r.content)
        return out
    except Exception:
        return ""


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


def collect_item_images(page):
    urls = set()
    # Prefer item card background images from Menufy markup.
    wrappers = page.query_selector_all(".item-link .item-image-wrapper, .item-image-wrapper")
    for w in wrappers:
        try:
            style = w.get_attribute("style") or ""
        except Exception:
            continue
        m = re.search(r"url\(['\"]?(https?://[^'\"\)]+)", style, flags=re.IGNORECASE)
        if m:
            urls.add(m.group(1))

    selectors = [
        "new-menufy-menu img",
        "menu-context img",
        ".category img",
        ".menu-item img",
        "img[data-src]",
        "img",
    ]
    for sel in selectors:
        try:
            imgs = page.query_selector_all(sel)
        except Exception:
            continue
        for im in imgs:
            try:
                src = im.get_attribute("src") or im.get_attribute("data-src")
            except Exception:
                continue
            if not src:
                continue
            if "logo" in src.lower() or "icon" in src.lower():
                continue
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http"):
                urls.add(src)
    return list(urls)


def collect_menu_items(page):
    items = []
    seen = set()

    # Preferred: use exact Menufy item-card selectors.
    cards = page.query_selector_all(".item-link")
    for c in cards:
        try:
            name = clean_text((c.query_selector(".item-name") or c).inner_text())
        except Exception:
            name = ""
        if not name:
            continue

        try:
            desc_node = c.query_selector(".item-description")
            description = clean_text(desc_node.inner_text()) if desc_node else ""
        except Exception:
            description = ""

        price = ""
        try:
            price_node = c.query_selector(".item-price")
            if price_node:
                price_text = clean_text(price_node.inner_text())
                prices = extract_prices(price_text)
                if prices:
                    price = prices[0]
        except Exception:
            pass

        image_url = ""
        try:
            image_node = c.query_selector(".item-image-wrapper")
            if image_node:
                style = image_node.get_attribute("style") or ""
                m = re.search(r"url\(['\"]?(https?://[^'\"\)]+)", style, flags=re.IGNORECASE)
                if m:
                    image_url = m.group(1)
        except Exception:
            pass

        key = (name.lower(), price)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "item": name,
                "description": description,
                "price": price,
                "image_url": image_url,
            }
        )

    if items:
        return items

    # Fallback: pull from broad visible blocks
    blocks = page.query_selector_all("div, li, section, article")
    for b in blocks:
        try:
            text = clean_text(b.inner_text())
        except Exception:
            continue
        if len(text) < 4 or len(text) > 180:
            continue
        prices = extract_prices(text)
        if not prices:
            continue
        item_name = clean_text(re.sub(r"\$?\d+(?:\.\d{2})?", "", text))
        if len(item_name) < 2:
            continue
        key = (item_name.lower(), prices[0])
        if key in seen:
            continue
        seen.add(key)
        items.append({"item": item_name, "description": "", "price": prices[0], "image_url": ""})

    return items


def extract_coordinates(page):
    html = page.content()

    patterns = [
        r"_locationLat\s*=\s*(-?\d+(?:\.\d+)?)",
        r'"latitude"\s*:\s*"?(?P<lat>-?\d+(?:\.\d+)?)"?',
    ]
    lon_patterns = [
        r"_locationLng\s*=\s*(-?\d+(?:\.\d+)?)",
        r'"longitude"\s*:\s*"?(?P<lon>-?\d+(?:\.\d+)?)"?',
    ]

    lat = None
    lon = None

    for p in patterns:
        m = re.search(p, html, flags=re.IGNORECASE)
        if m:
            lat = m.group(1) if m.lastindex else m.groupdict().get("lat")
            if lat is None and m.groupdict().get("lat"):
                lat = m.groupdict()["lat"]
            if lat:
                break

    for p in lon_patterns:
        m = re.search(p, html, flags=re.IGNORECASE)
        if m:
            lon = m.group(1) if m.lastindex else m.groupdict().get("lon")
            if lon is None and m.groupdict().get("lon"):
                lon = m.groupdict()["lon"]
            if lon:
                break

    try:
        lat = float(lat) if lat is not None else None
    except Exception:
        lat = None
    try:
        lon = float(lon) if lon is not None else None
    except Exception:
        lon = None

    return lat, lon


def main():
    item_rows = []
    image_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print(f"Opening {TARGET['url']}")
        page.goto(TARGET["url"], wait_until="domcontentloaded", timeout=60000)
        time.sleep(2)

        # Try basic consent popups
        for sel in ["button:has-text('Accept')", "button:has-text('OK')", ".close", ".btn-close"]:
            try:
                page.click(sel, timeout=1200)
            except Exception:
                pass

        # Scroll to load lazy content
        for _ in range(8):
            try:
                page.evaluate("window.scrollBy(0, window.innerHeight);")
            except Exception:
                pass
            time.sleep(0.8)

        logo_url = get_logo_url(page)
        item_images = collect_item_images(page)
        menu_items = collect_menu_items(page)
        latitude, longitude = extract_coordinates(page)

        logo_local = ""
        if DOWNLOAD_IMAGES and logo_url:
            logo_local = download_image(logo_url, IMAGE_DIR, "logo.jpg")

        if logo_url:
            image_rows.append(
                {
                    "restaurant": TARGET["name"],
                    "type": "logo",
                    "image_url": logo_url,
                    "local_path": logo_local,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

        for i, img in enumerate(item_images, start=1):
            local = ""
            if DOWNLOAD_IMAGES:
                local = download_image(img, IMAGE_DIR, f"item_{i}.jpg")
            image_rows.append(
                {
                    "restaurant": TARGET["name"],
                    "type": "item_image",
                    "image_url": img,
                    "local_path": local,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

        for m in menu_items:
            item_rows.append(
                {
                    "restaurant": TARGET["name"],
                    "url": TARGET["url"],
                    "item": m["item"],
                    "description": m.get("description", ""),
                    "price": m["price"],
                    "image_url": m.get("image_url", ""),
                }
            )

        browser.close()

    pd.DataFrame(item_rows).to_csv("nguyens_kitchen_menu.csv", index=False)
    pd.DataFrame(image_rows).to_csv("nguyens_kitchen_images.csv", index=False)

    with open("nguyens_kitchen_menu.json", "w", encoding="utf-8") as f:
        json.dump(item_rows, f, ensure_ascii=False, indent=2)
    with open("nguyens_kitchen_images.json", "w", encoding="utf-8") as f:
        json.dump(image_rows, f, ensure_ascii=False, indent=2)

    print("Finished.")
    print("Files:")
    print(" - nguyens_kitchen_menu.csv")
    print(" - nguyens_kitchen_menu.json")
    print(" - nguyens_kitchen_images.csv")
    print(" - nguyens_kitchen_images.json")
    if DOWNLOAD_IMAGES:
        print(f" - {IMAGE_DIR}/ (downloaded logo/item images when available)")


if __name__ == "__main__":
    main()
