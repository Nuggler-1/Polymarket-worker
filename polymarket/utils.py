import asyncio 
from playwright.async_api._generated import Page

async def switch_to_page_by_title(context, title) -> Page:
    
    for page in context.pages:
        # print([await page.title()])
        if title == await page.title():
            await page.bring_to_front()  # Переключаемся на страницу
            # print(await page.title())
            return page
    await asyncio.sleep(0.5)
    return None  
        
async def close_page_by_title(context, title):
    # Iterate through all open pages in the context
    for page in context.pages:
        # Get the title of each page
        if await page.title() == title:
            # Close the page if the title matches
            await page.close()
            return
        await asyncio.sleep(1)