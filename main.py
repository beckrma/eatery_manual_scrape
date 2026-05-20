from playwright.sync_api import sync_playwright
from multiprocessing import Pool
from scraper import scraper

test_restaurant = [
    {"name": "Menufy", "url": "https://order.menufy.com/"}
]


def state_splits(state_locator, save_file): # goal of function is to create multiple partitions of states
    states_count = state_locator.count()
    splits = []
    split_partition = None
    split_total = 0
    for i in range(states_count):
        state_href = state_locator.nth(i).get_attribute("href")
        state_name = state_locator.nth(i).inner_text().replace(" ", "")
        if (f"{state_name}\n" in save_file):
            continue
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
    content = None
    while (True):
        user_in = input("Would you like to run scraper with save file? (Y/N): ")
        if (user_in == 'Y' or user_in == 'y'):
            with open("state_save.txt", "r") as f:
                content = f.readlines()
                break
            if (not content):
                print("Save file is empty!")
                exit()
        elif (user_in == 'N' or user_in == 'n'):
            content = []
            break
        else:
            print("Response not recognized, please try again.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=True to hide browser

        context = browser.new_context()
        main_page = context.new_page()
        for r in test_restaurant:
            print(f"\n🌐 Scraping {r['name']} ...")
            main_page.goto(r["url"])

            # -------- Iterating Through States --------
            states = main_page.locator(".state-columns a")
            state_partitions = state_splits(states, content)
            print(state_partitions)
            main_page.close()
            with Pool(processes=len(state_partitions)) as p:
                p.map(scraper.main_scraping, state_partitions)
    print(f"\n✅ Finished scraping!")
    exit()
            



if __name__ == "__main__":
    run()