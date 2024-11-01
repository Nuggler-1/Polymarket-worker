from polymarket.account_ui import Account as AccountUI
from polymarket.account_api import Account as AccountAPI
from playwright.async_api import async_playwright
from polymarket.fork_runner import ForkRunner
from polymarket.bets_runner import BetsRunner
from web3 import Web3 
from loguru import logger

import asyncio 
import random
import sys
import questionary

from eth_account import Account as AccountETH
from relay.relay import RelayAccount
from binance import binance
from utils.utils import get_proxy, async_sleep, sleep, get_deposit_wallet, get_contract, build_and_send_tx, clear_file, search_for_erc20_crosschain
from utils.constants import *
from config import *
from vars import CHAINS_DATA, ERC20_ABI, logo


logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> |  <level>{message}</level>",
    colorize=True
)


async def withdraw_from_polymarket(private_keys): 

    if RANDOMIZE == True: 
        random.shuffle(private_keys)

    for private_key in private_keys: 

        proxy = get_proxy(private_key, 'dict')
        account = AccountUI(private_key, proxy = proxy)

        async with async_playwright() as playwright: 
            browser = await account._init_browser(playwright)
            await asyncio.sleep(3)
            page = await account.preapre_page(browser)
            await account.withdraw(browser, page)

        if private_key != private_keys[-1]:     
            await async_sleep(WALLET_SLEEP)

async def withdraw_to_cex(private_keys): 

    if RANDOMIZE == True: 
        random.shuffle(private_keys)

    web3 = Web3(Web3.HTTPProvider(RPC['POLYGON']))
    for private_key in private_keys: 
        try: 
            account = web3.eth.account.from_key(private_key)
            deposit_address = get_deposit_wallet(private_key)
            contract = get_contract(web3, CHAINS_DATA['POLYGON']['USDC'], ERC20_ABI)
            balance = contract.functions.balanceOf(account.address).call()
            tx = contract.functions.transfer(deposit_address, balance)
            sent_tx = build_and_send_tx(web3, account, tx)
            if private_key != private_keys[-1]: 
                sleep(WALLET_SLEEP)
        except Exception as e: 
            logger.warning(f'failed to withdraw: {str(e)}')

async def get_polymarket_deposit_addresses(private_keys): 

    clear_file(DEFAULT_POLYMARKET_WALLETS)

    for private_key in private_keys: 

        proxy = get_proxy(private_key, 'dict')
        account = AccountUI(private_key, proxy = proxy)

        async with async_playwright() as playwright: 
            browser = await account._init_browser(playwright)
            await asyncio.sleep(3)  
            page = await account.preapre_page(browser)
            deposit_wallet = await account.get_deposit_wallet(browser, page)

        with open(DEFAULT_POLYMARKET_WALLETS, 'a',encoding='utf-8' ) as f:
            f.write(f'{account.address}:{deposit_wallet}\n')

        if private_key != private_keys[-1]: 
            await async_sleep([10,20])

async def deposit_to_polymarket_relay(private_keys): 

    for private_key in private_keys: 
        account = RelayAccount(private_key)
        deposit_address = get_deposit_wallet(private_key, DEFAULT_POLYMARKET_WALLETS)

        coin_data = search_for_erc20_crosschain(private_key, 'USDC', CHAINS_BRIDGE_FROM, MIN_BALANCE_TO_SEE)

        try:
            chain_from = coin_data['chain_id']
            token_from = coin_data['token_address']
        except: 
            continue

        tx = await account.bridge_tokens(chain_from, 137, token_from, CHAINS_DATA['POLYGON']['USDC'], recipient=deposit_address)

        if private_key != private_keys[-1]: 
            await async_sleep(WALLET_SLEEP)

async def approve_deposit_and_enable_trading(private_keys): 

    for private_key in private_keys: 

        account = AccountUI(private_key, proxy = get_proxy(private_key, mode = 'dict'))

        async with async_playwright() as playwright: 
            browser = await account._init_browser(playwright)
            await asyncio.sleep(3)
            page = await account.preapre_page(browser)

            await account.approve_pending_deposit(browser, page)
            await asyncio.sleep(5)
            await account.approve_tokens(browser, page)

        if private_key != private_keys[-1]: 
            await async_sleep([10,20])

def binance_deposit(private_keys): 

    for private_key in private_keys:

        address = get_deposit_wallet(private_key, DEFAULT_POLYMARKET_WALLETS)
        amount = random.uniform(AMOUNT_TO_DEPOSIT[0], AMOUNT_TO_DEPOSIT[1])
        amount = round(amount, random.randrange(0,2))
        binance.binance_withdraw(address, amount, 'USDC', 'MATIC', API_KEY, API_SECRET)

        if private_key != private_keys[-1]: 
            sleep(WALLET_SLEEP)


def main(): 

    with open(DEFAULT_PRIVATE_KEYS, 'r', encoding='utf-8') as f: 
        private_keys = f.read().splitlines()

    while True:

        choice = questionary.select(
                    "Select work mode:",
                    choices=[
                        "Get polymarket deposit addresses", 
                        "Deposit to polymarket with binance",
                        "Deposit to polymarket via relay",
                        "Approve deposit and enable trading",
                        "[REDACTED]",
                        "Open forks",
                        "Place bets",
                        "Drop all positions",
                        "Withdraw from polymarket to Polygon", 
                        "withdraw from Polygon to CEX",
                        "Run specific wallet", 
                        "Exit"
                    ]
                ).ask()
                
        match choice: 

            case "Get polymarket deposit addresses":
                asyncio.run(get_polymarket_deposit_addresses(private_keys))

            case "Deposit to polymarket via relay": 
                asyncio.run(deposit_to_polymarket_relay(private_keys))
                
            case "Approve deposit and enable trading": 
                asyncio.run(approve_deposit_and_enable_trading(private_keys))

            case "[REDACTED]": 
                logger.opt(raw=True).info('Whoops! Looks like nothing is here...\n')

            case "Deposit to polymarket with binance": 
                binance_deposit(private_keys)
            
            case "Withdraw from polymarket to Polygon": 
                asyncio.run(withdraw_from_polymarket(private_keys))

            case "withdraw from Polygon to CEX":
                asyncio.run(withdraw_to_cex(private_keys))

            case "Place bets": 
                bets = BetsRunner(private_keys)
                bets.run_bets()

            case "Run specific wallet": 

                    addresses = [AccountETH.from_key(private_key).address for private_key in private_keys]
                    choice = questionary.select(
                        "Select work mode:",
                        choices=[
                            *addresses
                        ]
                    ).ask()

                    index = addresses.index(choice)
                    private_keys = [private_keys[index]]

            case "Drop all positions": 
                for private_key in private_keys: 
                    account = AccountAPI(private_key, funder=get_deposit_wallet(private_key, DEFAULT_POLYMARKET_WALLETS), proxy=get_proxy(private_key))
                    account.drop_all_positions()
                    if private_key != private_keys[-1]: 
                        sleep(WALLET_SLEEP)

            case "Open forks": 
                forks = ForkRunner(private_keys,)
                asyncio.run(forks.run_forks())

            case "Exit": 
                sys.exit()

            case _:
                pass

if __name__ == '__main__': 
    
    logger.opt(raw=True).info(logo)
    print('\n\n')
    main()