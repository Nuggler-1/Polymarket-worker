from polymarket.account_ui import Account as AccountUI
from polymarket.account_api import Account as AccountAPI
from playwright.async_api import async_playwright
from polymarket.fork_runner import ForkRunner
from polymarket.bets_runner import BetsRunner
from polymarket.account_stats import WalletStats
from polymarket.smart_fork_runner import SmartForkRunner
from web3 import Web3 
from loguru import logger

import asyncio 
import random
import sys
import questionary

from rich.console import Console
from rich.table import Table
from eth_account import Account as AccountETH
from relay.relay import RelayAccount
from binance import binance
from utils.utils import get_proxy, async_sleep, sleep, get_deposit_wallet, get_contract, build_and_send_tx, clear_file, search_for_erc20_crosschain, split_list_into_sized_chunks
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

async def claim_all_bets(private_keys): 

    for private_key in private_keys: 

        account = AccountUI(private_key, proxy = get_proxy(private_key, mode = 'dict'))

        async with async_playwright() as playwright: 
            browser = await account._init_browser(playwright)
            await asyncio.sleep(3)
            page = await account.preapre_page(browser)

            await account.claim_bets(browser, page)

        if private_key != private_keys[-1]: 
            await async_sleep(WALLET_SLEEP)

async def change_nicknames(private_keys): 

    for private_key in private_keys: 

        account = AccountUI(private_key, proxy = get_proxy(private_key, mode = 'dict'))

        async with async_playwright() as playwright: 
            browser = await account._init_browser(playwright)
            await asyncio.sleep(3)
            page = await account.preapre_page(browser)

            await account.change_nickname(page)

        if private_key != private_keys[-1]: 
            await async_sleep(WALLET_SLEEP)

def binance_deposit(private_keys): 

    for private_key in private_keys:

        address = get_deposit_wallet(private_key, DEFAULT_POLYMARKET_WALLETS)
        amount = random.uniform(AMOUNT_TO_DEPOSIT[0], AMOUNT_TO_DEPOSIT[1])
        amount = round(amount, random.randrange(0,2))
        binance.binance_withdraw(address, amount, 'USDC', 'MATIC', API_KEY, API_SECRET)

        if private_key != private_keys[-1]: 
            sleep(WALLET_SLEEP)

async def check_stats(private_keys): 


    table = Table()
    table.add_column("Address")
    table.add_column("Polymarket address")
    table.add_column("Nick")
    table.add_column('Balance')
    table.add_column("Volume")
    table.add_column("Profit")
    table.add_column("Active positions")

    wallet_chunks = split_list_into_sized_chunks(private_keys, 15)
    for chunk in wallet_chunks: 
        tasks = []  
        for private_key in chunk: 
            address = AccountETH.from_key(private_key).address
            proxy_wallet = get_deposit_wallet(private_key, DEFAULT_POLYMARKET_WALLETS)
            proxy = get_proxy(private_key)
            account = WalletStats(address, proxy_wallet, proxy['http'] if proxy != None else None)
            tasks.append(asyncio.create_task(account.display_stats(table)))
        await asyncio.gather(*tasks)

    console = Console()
    console.print(table)
    total_profit = 0
    total_balance = 0

    cells = table.columns[5].cells
    for profit in cells:
        total_profit += float(str(profit))
    total_profit = round(total_profit, 2)

    cells = table.columns[3].cells
    for balance in cells:
        total_balance += float(str(balance))
    total_balance = round(total_balance, 2)
    
    print()
    logger.opt(colors=True).info(f"Total Profit: {'<green>' + str(total_profit) + '</green>' if total_profit > 0 else '<red>' + str(total_profit) + '</red>'}")
    logger.info(f"Total Balance: {total_balance}")
    print()
    """
    for private_key in private_keys:
        print() 
        address = AccountETH.from_key(private_key).address
        proxy_wallet = get_deposit_wallet(private_key, DEFAULT_POLYMARKET_WALLETS)
        proxy = get_proxy(private_key)
        account = WalletStats(address, proxy_wallet, proxy['http'] if proxy != None else None)

        await account.display_stats(table)

    console = Console()
    console.print(table)
    """

async def display_positions(private_keys): 

    for private_key in private_keys: 
        address = AccountETH.from_key(private_key).address
        proxy_wallet = get_deposit_wallet(private_key, DEFAULT_POLYMARKET_WALLETS)
        proxy = get_proxy(private_key)
        account = WalletStats(address, proxy_wallet, proxy['http'] if proxy != None else None)
        await account.display_positions()
        print()


def main(): 

    with open(DEFAULT_PRIVATE_KEYS, 'r', encoding='utf-8') as f: 
        private_keys = f.read().splitlines()

    if len(private_keys) == 0: 
        logger.warning('Please upload at least one private key!')
        sys.exit()

    while True:

        try:

            choice = questionary.select(
                        "Select work mode:",
                        choices=[
                            "Get polymarket deposit addresses [under construction]", 
                            "Deposit to polymarket with binance",
                            #"Deposit to polymarket via relay",
                            "Approve deposit and enable trading",
                            #"[REDACTED]",
                            "Open forks",
                            "Open smart forks",
                            "Place bets",
                            "Drop all positions",
                            "Claim all bets",
                            "Withdraw from polymarket to Polygon [under construction]", 
                            "withdraw from Polygon to CEX [under construction]",
                            "Check stats",
                            'Check open positions',
                            'Change nicknames',
                            "Run specific wallets", 
                            "Run range of wallets",
                            "Reset selection of wallets",
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
        
                case "Claim all bets": 
                    asyncio.run(claim_all_bets(private_keys))

                case "Change nicknames":
                    asyncio.run(change_nicknames(private_keys))

                case "Run specific wallets": 
                    while True: 
                        addresses = [AccountETH.from_key(private_key).address for private_key in private_keys]
                        choice = questionary.checkbox(
                            "Select wallets to run:",
                            choices=[
                                *addresses
                            ]
                        ).ask()


                        if len(choice) == 0: 
                            logger.warning('Please select at least one wallet (USE SPACE TO SELECT)')
                            continue    

                        new_private_keys = []
                        for address in choice: 
                            index = addresses.index(address)
                            new_private_keys.append(private_keys[index])

                        private_keys = new_private_keys
                        break

                case "Run range of wallets": 

                    while True: 

                        addresses = [AccountETH.from_key(private_key).address for private_key in private_keys]
                        choice = questionary.checkbox(
                            "Select range of wallets to run (first and last):",
                            choices=[
                                *addresses
                            ]
                        ).ask()

                        if len(choice) !=  2: 
                            logger.warning('Please select first and last wallet in range (ONLY 2 WALLETS)')
                            continue

                        first_index = addresses.index(choice[0])
                        last_index = addresses.index(choice[1])

                        private_keys = private_keys[first_index:last_index+1]
                        break
                
                case "Reset selection of wallets": 

                    with open(DEFAULT_PRIVATE_KEYS, 'r', encoding='utf-8') as f: 
                        private_keys = f.read().splitlines()

                case "Check stats": 
                    asyncio.run(check_stats(private_keys))

                case "Check open positions": 
                    asyncio.run(display_positions(private_keys))

                case "Drop all positions": 
                    for private_key in private_keys: 
                        account = AccountAPI(private_key, funder=get_deposit_wallet(private_key, DEFAULT_POLYMARKET_WALLETS), proxy=get_proxy(private_key))
                        account.drop_all_positions()
                        if private_key != private_keys[-1]: 
                            sleep(WALLET_SLEEP)

                case "Open forks": 
                    forks = ForkRunner(private_keys,)
                    asyncio.run(forks.run_forks())
                
                case "Open smart forks":
                    forks = SmartForkRunner(private_keys)
                    asyncio.run(forks.run_forks())

                case "Exit": 
                    sys.exit()

                case _:
                    pass
                
        except Exception as e: 
            logger.error(f'Failed to run work mode: {str(e)}')

if __name__ == '__main__': 
    
    logger.opt(raw=True).info(logo)
    print('\n\n')
    main()