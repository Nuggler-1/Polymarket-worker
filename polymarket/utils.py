import asyncio 
from playwright.async_api._generated import Page

async def switch_to_page_by_title(browser, title, timeout = 10) -> Page | None:
    for _ in range(10):
        for page in browser.pages:

            if title ==  await page.title():
                await page.bring_to_front()  
                return page

        await asyncio.sleep(timeout/10)

    return None  
        
async def close_page_by_title(browser, title) -> None:
    # Iterate through all open pages in the context
    for page in browser.pages:
        # Get the title of each page
        if await page.title() == title:
            # Close the page if the title matches
            await page.close()
            return
        await asyncio.sleep(1)

async def close_pages_except_current(browser, current_page:Page) -> None:
    current_title = await current_page.title()
    for page in browser.pages:
        if await page.title() != current_title:
            await page.close()
        await asyncio.sleep(1)

async def close_page_by_url(browser, url) -> None: 

    for page in browser.pages: 
        if url in page.url: 
            await page.close()
            return
    