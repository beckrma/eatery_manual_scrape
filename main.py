from playwright.sync_api import sync_playwright
from multiprocessing import Pool
from scraper import scraper

test_restaurant = [
    {"name": "Menufy", "url": "https://www.menufy.com/"}
]


def state_splits(state_locator): # goal of function is to create multiple partitions of states
    states_count = state_locator.count()
    splits = []
    split_partition = None
    split_total = 0
    for i in range(states_count):
        state_href = state_locator.nth(i).get_attribute("href")
        if (split_total) == 0:
            split_partition = []
            split_partition.append(state_href)
            split_total += 1
        elif (split_total) == 9:
            split_partition.append(state_href)
            splits.append(split_partition)
            split_total = 0
        else:
            split_partition.append(state_href)
            split_total += 1
    else:
        if split_total != 0:
            splits.append(split_partition)
    return splits



def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=True to hide browser

        context = browser.new_context()
        main_page = context.new_page()
        for r in test_restaurant:
            print(f"\n🌐 Scraping {r['name']} ...")
            main_page.goto(r["url"])

            # -------- Iterating Through States --------
            states = main_page.locator(".state-columns a")
            state_partitions = state_splits(states)
            main_page.close()
            with Pool(processes=len(state_partitions)) as p:
                p.map(scraper.main_scraping, state_partitions)
    print(f"\n✅ Finished scraping!")



if __name__ == "__main__":
    run()