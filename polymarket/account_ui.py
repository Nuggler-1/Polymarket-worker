from playwright.async_api import async_playwright
from fake_useragent import UserAgent
from loguru import logger
from eth_account import Account as ethAccount

from .utils import switch_to_page_by_title, close_page_by_title
from .constants import POLYMARKET_URL
from config import AMOUNT_TO_WITHDRAW, WITHDRAW_ALL
from utils.utils import generate_name, async_error_handler

import os 
import asyncio
import random


class Account(): 

    def __init__(self,private_key:str, proxy:dict = None) -> None:

        """
        proxy in format {
            address: 'address',
            port: 'port',
            pass: 'pass',
            login: 'login'
        }
        
        """
       
        self.pk = private_key
        self.proxy = proxy 
        self.address = ethAccount().from_key(private_key).address
        self.args = [
            '--disable-blink-features=AutomationControlled',
            f"--disable-extensions-except={os.path.abspath('Metamask')}",
            f"--load-extension={os.path.abspath('Metamask')}",
            f"--disable-infobars"
            


        ]

        self.ua = UserAgent().random


    
    async def _init_browser(self, playwright):
            
        browser = await playwright.chromium.launch_persistent_context(
            '',
            headless=False,
            user_agent=self.ua,
            proxy={
                "server": f"http://{self.proxy['address']}:{self.proxy['port']}",
                "username": self.proxy['login'],
                "password": self.proxy['password']
            } if self.proxy is not None else self.proxy,
            args=self.args
        )

        return browser
    
    async def _close_empty_pages(self, browser):
        
        while True:

            empty_page = await switch_to_page_by_title(browser, '')
            if empty_page == None:
                break
            await empty_page.close()

        return 
    
    async def _click_through_metamask_popup(self,browser,popup_await = 3):

        await asyncio.sleep(popup_await)
        popup_window = await switch_to_page_by_title(browser, 'MetaMask')

        while True: #click throw metamask messages

            try: 
                if popup_window == None: 
                    break
                
                polygon_message_button = popup_window.locator('h6.mm-box.mm-text.mm-text--body-sm.mm-box--color-inherit')
                if await polygon_message_button.count() > 0: 
                    await polygon_message_button.nth(1).click(timeout = 5000) 

                await popup_window.click('button.button.btn--rounded.btn-primary', timeout = 7000)

            except Exception as e:
                await asyncio.sleep(3)
                popup_window = await switch_to_page_by_title(browser, 'MetaMask')

    @async_error_handler('preparing wallet')
    async def _prepare_wallet(self, browser):

        await self._close_empty_pages(browser)
        page = await switch_to_page_by_title(browser, 'MetaMask')
        
        await asyncio.sleep(2)
        await page.click('input.onboarding__terms-checkbox', timeout=5000)
        await page.click('button.button.btn--rounded.btn-primary', timeout=5000)
        await page.click('input.mm-checkbox__input', timeout = 5000)
        await page.click('button.button.btn--rounded.btn-primary', timeout=5000)

        input = page.locator('input.form-field__input').nth(0)
        await input.fill('12345678')
        input = page.locator('input.form-field__input').nth(1)
        await input.fill('12345678')
        await page.click('input.check-box', timeout = 5000)
        await page.click('button.button.btn--rounded.btn-primary', timeout=5000)

        await page.click('[data-testid="secure-wallet-later"]', timeout = 5000)
        await page.click('input.check-box', timeout = 5000)
        await page.click('button.button.btn--rounded.btn-primary', timeout=5000)
        await page.click('button.button.btn--rounded.btn-primary', timeout=5000)
        await page.click('button.button.btn--rounded.btn-primary', timeout=5000)
        await page.click('button.button.btn--rounded.btn-primary', timeout=5000)
        await asyncio.sleep(1)

        await page.click('button.mm-button-primary', timeout=5000)
        
        await page.click('span.multichain-account-picker__label', timeout = 5000)
        await page.click('button.mm-button-base--size-lg', timeout = 5000)

        btn = page.locator('button.mm-box.mm-text.mm-button-base.mm-button-base--size-sm.mm-button-link.mm-text--body-md-medium.mm-box--padding-0.mm-box--padding-right-0.mm-box--padding-left-0.mm-box--display-inline-flex.mm-box--justify-content-center.mm-box--align-items-center.mm-box--color-primary-default.mm-box--background-color-transparent').nth(1)
        await btn.click()

        input = page.locator('#private-key-box')
        await input.fill(self.pk)
        await page.click('button.mm-button-primary', timeout=5000)
        
        await browser.new_page()
        await close_page_by_title(browser, 'MetaMask')
        
        logger.info(f'{self.address}: Wallet is ready')

    @async_error_handler('wallet connection to polymarket',)
    async def _connect_polymarket(self, browser):
        
        page = await browser.new_page()
        await page.goto(POLYMARKET_URL)
        await asyncio.sleep(random.uniform(1, 2))

        for i in range(3):
            try:
                connect_btn = await page.query_selector("xpath=//button[text()='Sign Up']")
                await connect_btn.click()

                connect_btn = await page.query_selector("xpath=//span[text()='MetaMask']")
                await connect_btn.click()
                await asyncio.sleep(random.uniform(1,2))

                await self._click_through_metamask_popup(browser) #click throw metamask messages

                marker = page.locator('li.c-hdHRLY.c-hdHRLY-idnXRsK-css')
                await marker.wait_for(state='visible', timeout=5000)
                
                logger.info(f'{self.address}: Connection to Polymarket successful')
                return page
        
            except Exception as e: 
                logger.warning(f'{self.address}: Connection to Polymarket failed: retrying...')
                close_btn = page.locator('button.c-dNoRFn').nth(1)
                if close_btn: 
                    await close_btn.click()
                await asyncio.sleep(10)
                if i == 2: 
                    return None

    @async_error_handler('register wallet')
    async def _register_polymarket(self, page):

        nick_input = await page.query_selector("input.c-lhwwDC.c-lhwwDC-ilmimau-css")

        if nick_input: 
            name = generate_name([4,11], [0,999])
            await nick_input.fill(name)
            await page.click('div.c-dhzjXW.c-jzpRnK.c-dhzjXW-ifVlWzK-css', timeout = 5000)
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ihYfRge-css', timeout = 5000)
            await page.click('button.c-gBrBnR.c-gBrBnR-puLuM-variant-tertiary.c-gBrBnR-iebrwUE-css', timeout = 5000)
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ieVLKo-css', timeout= 5000)
    
    @async_error_handler('visit polymarket main page', retries=1)
    async def _visit_polymarket(self, browser): 

        page = await self._connect_polymarket(browser)
        await asyncio.sleep(3)
        await self._register_polymarket(page)

        return page
    
    async def preapre_page(self, browser):
        
        await self._prepare_wallet(browser)

        page = await self._visit_polymarket(browser)

        return page
    
    @async_error_handler('claiming bets')
    async def claim_bets(self, browser, page):

        await page.goto(POLYMARKET_URL+'portfolio')
        await asyncio.sleep(3)
        logger.info(f'{self.address}: Checking for bets to claim')

        claim_buttons = page.locator('a.c-gBrBnR.c-gBrBnR-fbCeQT-variant-quaternary.c-gBrBnR-ehsAZX-height-md.c-gBrBnR-eJubdF-fontWeight-bold.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-gaXLJU-cv.c-gBrBnR-ihilFlW-css')
        events_to_claim = []
        if await claim_buttons.count() > 0: 
            for i in range(await claim_buttons.count()):
                event_link= await claim_buttons.nth(i).get_attribute('href')
                events_to_claim.append(POLYMARKET_URL+event_link)
        else: 
            logger.warning(f'{self.address}: No bets to claim')
            return None
        
        for event in events_to_claim: 
            await page.goto(event)
            await asyncio.sleep(5)

            auth_buttons = await page.locator('button.c-gBrBnR.c-loKlDK.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-bxvuTL-fontWeight-medium.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-icwKLDw-css').all()
            if len(auth_buttons) > 1: 
                for btn in auth_buttons: 
                    await btn.click(timeout = 5000)
                    await self._click_through_metamask_popup(browser, popup_await=10)
                    await asyncio.sleep(2)

            claim_button = page.locator('div.c-jpvvtk') 
            if await claim_button.count() > 0: 
                await claim_button.click(timeout = 5000)
                await self._click_through_metamask_popup(browser)
                logger.success(f'{self.address}: Bet {event.split("/")[-1]} claimed')
                await asyncio.sleep(3) 
    
    @async_error_handler('approving tokens')
    async def approve_tokens(self, browser, page):
        
        
        await page.goto(POLYMARKET_URL)
        await asyncio.sleep(3)

        await page.click('div.c-dhzjXW.c-dhzjXW-ijblzia-css', timeout = 5000)
        await asyncio.sleep(3)
        
        
        button = await page.locator('button.c-gBrBnR.c-loKlDK.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-bxvuTL-fontWeight-medium.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-icwKLDw-css').all()
        if len(button) > 1: 
            await button[0].click(timeout = 5000)
            await self._click_through_metamask_popup(browser, popup_await=10)
            await asyncio.sleep(2)

            button = page.locator('button.c-gBrBnR.c-loKlDK.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-bxvuTL-fontWeight-medium.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-icwKLDw-css')
            await button.click(timeout = 5000)
            await self._click_through_metamask_popup(browser, popup_await=10)
        else: 
            logger.warning(f'{self.address}: No approve needed')

        logger.success(f'{self.address}: Tokens approved and trading enabled')

        return 1

    @async_error_handler('getting deposit address')
    async def get_deposit_wallet(self,browser, page): 

        await page.goto(POLYMARKET_URL+'wallet')
        await asyncio.sleep(5)

        try: 
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ifzfUjP-css', timeout = 5000)
            await self._click_through_metamask_popup(browser)
            await asyncio.sleep(20)
        except: 
            pass

        deposit_address = await page.query_selector('input.c-lhwwDC.c-lhwwDC-ihSEsrb-css.c-cwjPQu.c-cwjPQu-hSPtVx-cursor-true.c-cwjPQu-ikWyXas-css')
        deposit_address = await deposit_address.input_value()
        logger.success(f'{self.address}: deposit address found: {deposit_address}')

        return deposit_address

    @async_error_handler('approve deposit')
    async def approve_pending_deposit(self, browser, page):

        await page.goto(POLYMARKET_URL+'wallet')
        await asyncio.sleep(5)

        try: 
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ifzfUjP-css', timeout = 5000)
            await self._click_through_metamask_popup(browser)
        except: 
            pass

        try: 
            await page.click('p.c-dqzIym.c-dqzIym-fxyRaa-color-normal.c-dqzIym-cTvRMP-spacing-normal.c-dqzIym-iIobgq-weight-medium.c-dqzIym-hzzdKO-size-md.c-dqzIym-ieXspgQ-css', timeout = 5000)
            await page.click('button.c-hDtDII.c-hDtDII-fcAbGk-color-blue.c-hDtDII-kCmBzA-async-true.c-hDtDII-icSrXKB-css.c-PJLV', timeout = 5000)
            await self._click_through_metamask_popup(browser, popup_await=10)

            logger.success(f'{self.address}: Deposit confirmed')
            return 1
        
        except: 
            logger.warning(f'{self.address}: No pending deposit message found')
            return None
        

    @async_error_handler('withdrawing USDC')
    async def withdraw(self, browser, page):

        await page.goto(POLYMARKET_URL+'wallet')
        await asyncio.sleep(5)
        
        try: 
            await page.click('xpath=//button[text()="Withdraw"]', timeout = 5000)
            await page.click('xpath=//p[text()="Use connected"]', timeout = 5000)

            if WITHDRAW_ALL: 
                await page.click('p.c-dqzIym.c-gukFRq.c-dqzIym-fxyRaa-color-normal.c-dqzIym-cTvRMP-spacing-normal.c-dqzIym-iIobgq-weight-medium.c-dqzIym-ijlApXB-css', timeout = 5000)
            else:
                input = page.locator('input.c-lhwwDC.c-lhwwDC-ibnpMQW-css').nth(1)
                amount = random.uniform(AMOUNT_TO_WITHDRAW[0], AMOUNT_TO_WITHDRAW[1])
                amount = round(amount, random.randrange(0, 2))
                await input.fill(str(amount))
            
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-eBERDr-height-lg.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-igULOkw-css', timeout = 5000)
            await self._click_through_metamask_popup(browser, popup_await=10)

            logger.success(f'{self.address}: Withdrawal completed')
            return 1
            
        except Exception as e: 
            logger.error(f'{self.address}: Withdrawal failed: error message: {str(e)}')
            return None

        


        

