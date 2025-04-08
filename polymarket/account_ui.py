from playwright.async_api import Page
from fake_useragent import UserAgent
from loguru import logger
from eth_account import Account as ethAccount

from .utils import switch_to_page_by_title, close_page_by_title
from .constants import POLYMARKET_URL
from config import AMOUNT_TO_WITHDRAW, WITHDRAW_ALL, TIMEOUT, ERR_ATTEMPTS, PROXY_MODE
from utils.utils import generate_name, async_error_handler, async_sleep

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
                "server": f"{PROXY_MODE.lower()}://{self.proxy['address']}:{self.proxy['port']}",
                "username": self.proxy['login'],
                "password": self.proxy['password']
            } if self.proxy is not None else self.proxy,
            args=self.args
        )

        return browser
    
    async def _close_empty_pages(self, browser):
        
        while True:

            empty_page = await switch_to_page_by_title(browser, '', timeout = 1)
            if empty_page == None:
                break
            await empty_page.close()

        return 
    
    async def _click_through_metamask_popup(self,browser,timeout_multplier = 1):

        popup_window = await switch_to_page_by_title(browser, 'MetaMask', timeout = int(30 * timeout_multplier))

        while True: #click through metamask messages

            try: 
                if popup_window == None: 
                    break
                
                polygon_message_button = popup_window.locator('h6.mm-box.mm-text.mm-text--body-sm.mm-box--color-inherit')
                if await polygon_message_button.count() > 0: 
                    await polygon_message_button.nth(1).click(timeout = TIMEOUT) 

                await popup_window.click('button.button.btn--rounded.btn-primary', timeout = int(1.5*TIMEOUT))

            except Exception as e:
                await asyncio.sleep(3)
                popup_window = await switch_to_page_by_title(browser, 'MetaMask')

    @async_error_handler('preparing wallet')
    async def _prepare_wallet(self, browser):

        page = await switch_to_page_by_title(browser , 'MetaMask', timeout = 4*TIMEOUT/1_000)
        await self._close_empty_pages(browser)
        
        await page.click('input.onboarding__terms-checkbox', timeout = TIMEOUT)
        await page.click('button.button.btn--rounded.btn-primary', timeout = TIMEOUT)
        await page.click('input.mm-checkbox__input', timeout = TIMEOUT)
        await page.click('button.button.btn--rounded.btn-primary', timeout = TIMEOUT)

        input = page.locator('input.form-field__input').nth(0)
        await input.fill('12345678')
        input = page.locator('input.form-field__input').nth(1)
        await input.fill('12345678')
        await page.click('input.check-box', timeout = TIMEOUT)
        await page.click('button.button.btn--rounded.btn-primary', timeout = TIMEOUT)

        await page.click('[data-testid="secure-wallet-later"]', timeout = TIMEOUT)
        await page.click('input.check-box', timeout = TIMEOUT)
        await page.click('button.button.btn--rounded.btn-primary', timeout = TIMEOUT)
        await page.click('button.button.btn--rounded.btn-primary', timeout = TIMEOUT)
        await page.click('button.button.btn--rounded.btn-primary', timeout = TIMEOUT)
        await page.click('button.button.btn--rounded.btn-primary', timeout = TIMEOUT)
        await asyncio.sleep(1)

        await page.click('button.mm-button-primary', timeout = TIMEOUT)
        
        await page.click('span.multichain-account-picker__label', timeout = TIMEOUT)
        await page.click('button.mm-button-base--size-lg', timeout = TIMEOUT)

        btn = page.locator('button.mm-box.mm-text.mm-button-base.mm-button-base--size-sm.mm-button-link.mm-text--body-md-medium.mm-box--padding-0.mm-box--padding-right-0.mm-box--padding-left-0.mm-box--display-inline-flex.mm-box--justify-content-center.mm-box--align-items-center.mm-box--color-primary-default.mm-box--background-color-transparent').nth(1)
        await btn.click()

        input = page.locator('#private-key-box')
        await input.fill(self.pk)
        await page.click('button.mm-button-primary', timeout = TIMEOUT)
        
        await browser.new_page()
        await close_page_by_title(browser, 'MetaMask')
        
        logger.info(f'{self.address}: Wallet is ready')

    @async_error_handler('wallet connection to polymarket',)
    async def _connect_polymarket(self, browser):
        
        for i in range(3):
            try:

                page = await browser.new_page()
                await self._load_page(page, POLYMARKET_URL)

                connect_btn = await page.wait_for_selector("xpath=//button[text()='Sign Up']", timeout = TIMEOUT)
                await connect_btn.click()

                await self._check_element_exists_and_visible(page, 'button.c-fIAueE') #wait for metamask button to appear
                mm_btn = page.locator('button.c-fIAueE').nth(0)
                await mm_btn.click()

                await self._click_through_metamask_popup(browser) #click through metamask messages

                marker = page.locator('xpath=//button[text()="Deposit"]')
                await marker.wait_for(state='visible', timeout=TIMEOUT)
                
                logger.info(f'{self.address}: Connection to Polymarket successful')
                account_banned = await self._check_element_exists_and_visible(page, 'xpath=//h2[text()="Trading Halted"]', timeout = int(TIMEOUT/2))
                if account_banned:
                    logger.warning(f'{self.address}: Account trading is banned')

                return page
        
            except Exception as e: 
                logger.warning(f'{self.address}: Connection to Polymarket failed: {str(e)} - retrying...')
                close_btn = page.locator('button.c-dNoRFn').nth(1)
                if close_btn: 
                    await close_btn.click()
                
                restricted = await self._check_element_exists_and_visible(page, 'button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ibQoyvR-css', timeout = TIMEOUT)
                if restricted:                 
                    btn = page.locator('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ibQoyvR-css').all()
                    await btn.click(timeout = TIMEOUT)
                    return page
                    
                await asyncio.sleep(10)
                if i == 2: 
                    return None

    @async_error_handler('register wallet')
    async def _register_polymarket(self, page):

        if await self._check_element_exists_and_visible(page,"input.c-lhwwDC.c-lhwwDC-ilmimau-css", timeout = TIMEOUT): 
            
            name = generate_name([4,11], [0,999])
            nick_input = await page.query_selector("input.c-lhwwDC.c-lhwwDC-ilmimau-css")
            await nick_input.fill(name)
            await page.click('div.c-dhzjXW.c-jzpRnK.c-dhzjXW-ifVlWzK-css', timeout = TIMEOUT)
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ihYfRge-css', timeout = TIMEOUT)
            await page.click('button.c-gBrBnR.c-gBrBnR-puLuM-variant-tertiary.c-gBrBnR-iebrwUE-css', timeout = TIMEOUT)
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ieVLKo-css', timeout= TIMEOUT)
    
    @async_error_handler('visit polymarket main page', retries=1)
    async def _visit_polymarket(self, browser): 

        page = await self._connect_polymarket(browser)
        await asyncio.sleep(3)
        await self._register_polymarket(page)

        return page
    
    async def _check_element_exists_and_visible(self, page:Page, selector:str, timeout:int = TIMEOUT): 
        
        try:
            await page.wait_for_selector(selector,state='visible', timeout = timeout)
            return True
        except Exception:
            return False
        
    async def _load_page(self, page:Page, url:str, timeout = 4*TIMEOUT): 

        for _ in range(ERR_ATTEMPTS):
            try:
                await page.goto(url,wait_until="load", timeout = timeout)
                return 
            except Exception:
                await asyncio.sleep(3)
                continue

        raise Exception(f'{self.address}: Failed to load page {url}')
    
    async def preapre_page(self, browser):
        
        await self._prepare_wallet(browser)

        page = await self._visit_polymarket(browser)

        return page
    
    @async_error_handler('claiming bets')
    async def claim_bets(self, browser, page):

        await self._load_page(page,POLYMARKET_URL+'portfolio')
        logger.info(f'{self.address}: Checking for bets to claim')
                                                                    
        claim = await self._check_element_exists_and_visible(page, 'button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-eJubdF-fontWeight-bold.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-faTPNG-cv.c-gBrBnR-iiVZvnu-css', timeout=TIMEOUT)
        if claim: 
            logger.info(f'{self.address}: Claiming bets')
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-eJubdF-fontWeight-bold.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-faTPNG-cv.c-gBrBnR-iiVZvnu-css', timeout = TIMEOUT)
            await self._check_element_exists_and_visible(page, 'button.c-gBrBnR.c-chRxwd.c-gBrBnR-gDWzxt-variant-primary', timeout=TIMEOUT)
            await page.click('button.c-gBrBnR.c-chRxwd.c-gBrBnR-gDWzxt-variant-primary',timeout = TIMEOUT)
            await self._click_through_metamask_popup(browser, timeout_multplier=2)
            claimed = await self._check_element_exists_and_visible(page, 'xpath=//p[text()="You successfully claimed all your winnings."]', timeout=TIMEOUT)
            if claimed:
                logger.success(f'{self.address}: Bets claimed')
                await async_sleep([2,5])
                return 1
            else: 
                raise Exception(f'{self.address}: Bets claim failed. Could not find confirmation message')
        else: 
            logger.warning(f'{self.address}: No bets to claim')
            return None
    
    @async_error_handler('approving tokens')
    async def approve_tokens(self, browser, page):
        
        await self._load_page(page, POLYMARKET_URL)
        await page.click('div.c-dhzjXW.c-dhzjXW-ijblzia-css', timeout = TIMEOUT)
        
        approve = await self._check_element_exists_and_visible(page,'button.c-gBrBnR.c-loKlDK.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-bxvuTL-fontWeight-medium.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-icwKLDw-css', timeout = TIMEOUT)
        if approve: 
            buttons = await page.locator('button.c-gBrBnR.c-loKlDK.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-bxvuTL-fontWeight-medium.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-icwKLDw-css').all()
            if len(buttons) > 1:
                await buttons[0].click(timeout = TIMEOUT)
                await self._click_through_metamask_popup(browser)
                await asyncio.sleep(2)

                button = page.locator('button.c-gBrBnR.c-loKlDK.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-bxvuTL-fontWeight-medium.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-icwKLDw-css')
                await button.click(timeout = TIMEOUT)
                await self._click_through_metamask_popup(browser)
            else: 
                logger.warning(f'{self.address}: No approve needed')

        logger.success(f'{self.address}: Tokens approved and trading enabled')

        return 1

    @async_error_handler('getting deposit address')
    async def get_deposit_wallet(self,browser, page): 

        await self._load_page(page, POLYMARKET_URL+'wallet')

        try: 
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ifzfUjP-css', timeout = TIMEOUT)
            await self._click_through_metamask_popup(browser)
        except: 
            pass

        deposit_address = await page.wait_for_selector('input.c-lhwwDC.c-lhwwDC-ihSEsrb-css.c-cwjPQu.c-cwjPQu-hSPtVx-cursor-true.c-cwjPQu-ikWyXas-css', timeout = TIMEOUT)
        deposit_address = await deposit_address.input_value()
        logger.success(f'{self.address}: deposit address found: {deposit_address}')

        return deposit_address

    @async_error_handler('changing nickname')
    async def change_nickname(self, page):
        await self._load_page(page, POLYMARKET_URL +"settings")

        if await self._check_element_exists_and_visible(page,"input.c-lhwwDC.c-lhwwDC-ihicnEK-css", timeout = TIMEOUT): 
            
            name = generate_name([4,11], [0,999])
            nick_input = await page.query_selector("input.c-lhwwDC.c-lhwwDC-ihicnEK-css")
            await nick_input.fill(name)
            await asyncio.sleep(2)
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ieKNWzS-css', timeout = TIMEOUT)
            await async_sleep([5,10])
            logger.success(f'{self.address} nickname changed to {name}')

    @async_error_handler('approve deposit')
    async def approve_pending_deposit(self, browser, page):

        await self._load_page(page, POLYMARKET_URL+'wallet')

        try: 
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-ifzfUjP-css', timeout = TIMEOUT)
            await self._click_through_metamask_popup(browser)
        except: 
            pass

        try: 
            await page.click('p.c-dqzIym.c-dqzIym-fxyRaa-color-normal.c-dqzIym-cTvRMP-spacing-normal.c-dqzIym-iIobgq-weight-medium.c-dqzIym-hzzdKO-size-md.c-dqzIym-ieXspgQ-css', timeout = TIMEOUT)
            await page.click('button.c-hDtDII.c-hDtDII-fcAbGk-color-blue.c-hDtDII-kCmBzA-async-true.c-hDtDII-icSrXKB-css.c-PJLV', timeout = TIMEOUT)
            await self._click_through_metamask_popup(browser)

            logger.success(f'{self.address}: Deposit confirmed')
            return 1
        
        except: 
            logger.warning(f'{self.address}: No pending deposit message found')
            return None
        

    @async_error_handler('withdrawing USDC')
    async def withdraw(self, browser, page):

        await self._load_page(page, POLYMARKET_URL+'wallet')
        
        try: 
            await page.click('xpath=//button[text()="Withdraw"]', timeout = TIMEOUT)
            await page.click('xpath=//p[text()="Use connected"]', timeout = TIMEOUT)

            if WITHDRAW_ALL: 
                await page.click('p.c-dqzIym.c-gukFRq.c-dqzIym-fxyRaa-color-normal.c-dqzIym-cTvRMP-spacing-normal.c-dqzIym-iIobgq-weight-medium.c-dqzIym-ijlApXB-css', timeout = TIMEOUT)
            else:
                input = page.locator('input.c-lhwwDC.c-lhwwDC-ibnpMQW-css').nth(1)
                amount = random.uniform(AMOUNT_TO_WITHDRAW[0], AMOUNT_TO_WITHDRAW[1])
                amount = round(amount, random.randrange(0, 2))
                await input.fill(str(amount))
            
            await page.click('button.c-gBrBnR.c-gBrBnR-gDWzxt-variant-primary.c-gBrBnR-eBERDr-height-lg.c-gBrBnR-dRRWyf-fontSize-md.c-gBrBnR-igULOkw-css', timeout = TIMEOUT)
            await self._click_through_metamask_popup(browser)

            logger.success(f'{self.address}: Withdrawal completed')
            return 1
            
        except Exception as e: 
            logger.error(f'{self.address}: Withdrawal failed: error message: {str(e)}')
            return None

        


        

