import random
import questionary
import asyncio
import sys
from web3 import Web3
from loguru import logger
from .account_api import Account as AccountAPI

from config import TOTAL_AMOUNT, RPC,BETS_DEVIATION_PERCENT, SLEEP_BETWEEN_WALLETS_IN_FORK, SLEEP_BETWEEN_FORKS
from vars import CHAINS_DATA
from utils.constants import DEFAULT_POLYMARKET_WALLETS, SAVED_FORK_WALLETS
from polymarket.market_search import Search
from utils.utils import get_erc20_balance, get_deposit_wallet, sleep, get_proxy


class ForkRunner(Search):

    def __init__(self, private_keys: list[str], ):

        super().__init__()

        self.private_keys = private_keys
        self.accounts = []

        self.events_to_check, self.min_liquidity, self.max_loss, self.max_price_difference = self._ask_data()

        self.web3 = Web3(Web3.HTTPProvider(RPC['POLYGON']))
        logger.info(f'Creating list of accounts - it might take a while...')
        for key in private_keys:
            self.accounts.append(AccountAPI(key, funder = get_deposit_wallet(key, deposit_addresses=DEFAULT_POLYMARKET_WALLETS), proxy = get_proxy(key) ) )

        self.market_list = None
        self.set_market_list()

    def set_market_list(self,):

        logger.info(f'Finding markets according to filters to open bets')
        self.market_list = asyncio.run(self.find_markets(self.events_to_check, self.min_liquidity, self.max_loss, self.max_price_difference))
        if len(self.market_list) == 0:
            logger.warning('No markets found according to filters')
            return False 
        else: 
            print()
            logger.success(f'Found {len(self.market_list)} markets according to filters')
            for name, tokens in self.market_list.items():
                logger.opt(colors=True).success(f'YES <cyan>{list(tokens.values())[0]:.3f}$</cyan> - NO <cyan>{list(tokens.values())[1]:.3f}$</cyan> - {name}')
            return True
        
    async def get_market(self,):

        while True:

            if len(self.market_list) == 0:
                logger.info('No markets left according to filters, starting refresh...')
                self.set_market_list()
                continue

            market_name, tokens = random.choice(list(self.market_list.items()))
            tokens = list(tokens.keys())
            res = await self._process_market_prices(market_name, tokens)

            if not res: 
                logger.warning(f'Market {market_name} is no longer suitable for filters, trying again')
                del self.market_list[market_name]
                continue
            else: 
                return res
            
    async def _find_accounts(self,): 

        main_account = None
        hedge_account_1 = None
        hedge_account_2 = None
        total_amount = random.uniform(TOTAL_AMOUNT[0], TOTAL_AMOUNT[1])

        print()
        
        _market_data = await self.get_market()

        name = list(_market_data.keys())[0]
        main_token_id, hedge_token_id = _market_data[name].keys()
        main_price, hedge_price = _market_data[name].values()
        #на основании цен и тотал амаунт считаем суммы ставок 

        main_amount, hedge_amount, _ = self.calculate_balanced_bets_amounts(total_amount, main_price, hedge_price) 
        deviation = random.uniform(-BETS_DEVIATION_PERCENT/2, BETS_DEVIATION_PERCENT/2)/100

        main_amount = main_amount + main_amount * deviation
        hedge_amount = hedge_amount + hedge_amount * deviation
        hedge_amount_1 = hedge_amount * random.uniform(0.4,0.6)
        hedge_amount_2 = hedge_amount - hedge_amount_1

        random.shuffle(self.accounts)
        for account in self.accounts:
            balance = get_erc20_balance(self.web3, account.funder, CHAINS_DATA['POLYGON']['USDC.e'])
            if balance >= main_amount:
                main_account = account
                self.accounts.remove(account)
                break

        random.shuffle(self.accounts)
        for account in self.accounts:
            balance = get_erc20_balance(self.web3, account.funder, CHAINS_DATA['POLYGON']['USDC.e'])
            if balance >= hedge_amount_1:
                hedge_account_1 = account
                self.accounts.remove(account)
                break

        random.shuffle(self.accounts)
        for account in self.accounts:
            balance = get_erc20_balance(self.web3, account.funder, CHAINS_DATA['POLYGON']['USDC.e'])
            if balance >= hedge_amount_1:
                hedge_account_2 = account
                self.accounts.remove(account)
                break

        if main_account is None or hedge_account_1 is None or hedge_account_2 is None:
            return None
        else:
            return {
                'main_account': main_account,
                'hedge_account_1': hedge_account_1,
                'hedge_account_2': hedge_account_2,
                'main_amount': main_amount,
                'hedge_amount_1': hedge_amount_1,
                'hedge_amount_2': hedge_amount_2,
                'main_token_id': main_token_id,
                'hedge_token_id': hedge_token_id
            }
        
    def _ask_data(self,):
        amount_of_events = str(
            questionary.text("Input amount of events to check (default is 20): \n").ask()
        )
        amount_of_events = 20 if len(amount_of_events) == 0 else int(amount_of_events)

        min_liquidity = str(
            questionary.text("Input min liquidity in market orderbook (default is 150$): \n").ask()
        )
        min_liquidity = 150 if len(min_liquidity) == 0 else float(min_liquidity)

        max_loss = str(
            questionary.text("Input max loss in % (default is 5%): \n").ask()
        )
        max_loss = 5 if len(max_loss) == 0 else float(max_loss) 

        max_price_difference = str(
            questionary.text("Input max price difference in cents [2 - 98] (default is 20 e.g. max difference of bets is 60 to 40): \n").ask()
        )
        max_price_difference = 20 if len(max_price_difference) == 0 else float(max_price_difference) 

        return amount_of_events, min_liquidity, max_loss, max_price_difference
        
    async def run_forks(self, ):

        for _ in range(0, len(self.private_keys), 2):

            data = await self._find_accounts()
            if data is None:
                logger.warning('No accounts to open forks')
                continue

            main_account = data['main_account']
            hedge_account_1 = data['hedge_account_1']
            hedge_account_2 = data['hedge_account_2']
            main_amount = data['main_amount']
            hedge_amount_1 = data['hedge_amount_1']
            hedge_amount_2 = data['hedge_amount_2']
            main_token_id = data['main_token_id']
            hedge_token_id = data['hedge_token_id'] 

            # Сохраняем данные кошельков в файл
            with open(SAVED_FORK_WALLETS, 'a') as f:
                f.write(f"{main_account._private_key},{hedge_account_1._private_key},{hedge_account_2._private_key}\n")

            logger.opt(colors=True).info(f'Starting accounts with <cyan><bold>{main_account.address}</bold></cyan> as main side')
            logger.opt(colors=True).info(f'And <magenta><bold>{hedge_account_1.address}</bold></magenta> & <magenta><bold>{hedge_account_2.address}</bold></magenta> as hedge side')
            order = main_account.market_buy(main_token_id, main_amount)
            if not order: 
                logger.warning(f'{main_account.address} - Main order failed to fill')
                continue 

            sleep(SLEEP_BETWEEN_WALLETS_IN_FORK)
            order_hedge_1 = hedge_account_1.market_buy(hedge_token_id, hedge_amount_1)
            sleep(SLEEP_BETWEEN_WALLETS_IN_FORK)
            order_hedge_2 = hedge_account_2.market_buy(hedge_token_id, hedge_amount_2)

            if not order_hedge_1 or not order_hedge_2: 
                logger.warning(f'{hedge_account_1.address if not order_hedge_1 else hedge_account_2.address} - Hedge order failed to fill')
                logger.info(f'Closing all active positions on market in pair')
                if not main_account.sell_all_positions_on_market(main_token_id):
                    logger.warning(f'{main_account.address} - Failed to close all positions on market, please check manually')
                if not hedge_account_1.sell_all_positions_on_market(hedge_token_id):
                    logger.warning(f'{hedge_account_1.address} - Failed to close all positions on market, please check manually')
                if not hedge_account_2.sell_all_positions_on_market(hedge_token_id):
                    logger.warning(f'{hedge_account_2.address} - Failed to close all positions on market, please check manually')
                continue 

            sleep(SLEEP_BETWEEN_FORKS)








        


        

