import csv
import time
import asyncio
from tqdm import tqdm
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page
from config import BASE_URL, PRODUCT_START_URL


async def create_browser():
    pw = await async_playwright().start()
    return await pw.chromium.launch(headless=True), pw


async def click_show_more_button(page: Page):
    # Get the initial content
    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")
    max_clicks = int(soup.find_all("a", class_="ib")[-2].get_text()) - 1

    with tqdm(total=max_clicks, desc="Clicking 'Show More' button", unit="click") as pbar:
        for _ in range(max_clicks):
            try:
                more_btn_div = await page.wait_for_selector(
                    ".list-more-div", timeout=1000
                )
                if more_btn_div:
                    await more_btn_div.click()
                    await asyncio.sleep(1.5)
                    pbar.update(1)
                else:
                    break
            except Exception:
                print("Finished scraping or something went wrong :)")
                break


async def parse_single_product(url, page):
    chars = {}
    await page.goto(PRODUCT_START_URL + url)
    soup = BeautifulSoup(await page.content(), "html.parser")

    model_name = soup.find("div", class_="cont-block-title").find("span", class_="blue").contents[0]

    item_conf = soup.find("span", class_="item-conf-name").get_text(strip=True)
    if '"' in item_conf:
        color = item_conf.split('"')[1].strip()
    else:
        color = item_conf

    chars["url"] = PRODUCT_START_URL + url
    chars["model"] = model_name
    chars["color"] = color

    characteristics = soup.find_all("div", class_="m-s-f3")
    for characteristic in characteristics:
        content = characteristic.get("title")
        name, data = content.split(": ")
        data = data.replace("\xa0", " ")
        if "," in data:
            data = data.split(",")
        chars[name] = data

    return chars


async def parse_all_products(soup, browser):
    products_list = []
    products = soup.find_all("a", class_="model-short-title")
    print(f"Found {len(products)} products")

    semaphore = asyncio.Semaphore(20)

    async def process_product(product):
        async with semaphore:
            page = await browser.new_page()
            try:
                result = await parse_single_product(product.get("href"), page)
                return result
            finally:
                await page.close()

    tasks = [process_product(product) for product in products]

    for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Parsing products", unit="product"):
        result = await task
        products_list.append(result)

    return products_list


async def scrape_all_products():
    browser, pw = await create_browser()
    page = await browser.new_page()
    await page.goto(BASE_URL)

    # Now using the async version of click_show_more_button
    await click_show_more_button(page)

    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")
    products_list = await parse_all_products(soup, browser)

    if products_list:
        keys = products_list[0].keys()
        with open("products.csv", mode="w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=keys)
            writer.writeheader()
            writer.writerows(products_list)

    await page.close()
    await browser.close()
    await pw.stop()


async def main():
    await scrape_all_products()


if __name__ == "__main__":
    asyncio.run(main())