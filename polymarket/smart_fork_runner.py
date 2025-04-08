import random
import questionary
import asyncio
from web3 import Web3
from loguru import logger
from .account_api import Account as AccountAPI

from config import ERR_ATTEMPTS, TOTAL_AMOUNT, RPC,BETS_DEVIATION_PERCENT, SLEEP_BETWEEN_WALLETS_IN_FORK, SLEEP_BETWEEN_FORKS,BET_MORE_ON_HIGHEST_CHANCE
from vars import CHAINS_DATA
from utils.constants import DEFAULT_POLYMARKET_WALLETS
from .constants import GAMMA_API
from polymarket.market_search import Search
from utils.utils import get_erc20_balance, get_deposit_wallet, sleep, async_sleep, get_proxy
from requests import Session
import time
import datetime
import json


class SmartForkRunner(Search):

    def __init__(self, private_keys: list[str], ):

        super().__init__()

        self.private_keys = private_keys
        self.accounts = []

        self.slug_of_events = None
        self.market_resolve_days = None
        self.acc_qnty_per_fork = None
        self.max_amount_per_wallet = None
        self.min_event_price = None
        self.max_event_price = None
        self.max_loss = None

        self._ask_data()
    
        self.web3 = Web3(Web3.HTTPProvider(RPC['POLYGON']))
        logger.info(f'Creating list of accounts - it might take a while...')
        for key in private_keys:
            self.accounts.append(AccountAPI(key, funder = get_deposit_wallet(key, deposit_addresses=DEFAULT_POLYMARKET_WALLETS), proxy = get_proxy(key) ) )

        self.market_list = None

    async def _process_single_market(self, market:dict):
        
        tokens = json.loads(market['clobTokenIds'])

        price_1 =  int(await self._get_market_price(tokens[0],  self.min_liquidity)*100) 
        price_2 =  int(await self._get_market_price(tokens[1],  self.min_liquidity)*100)

        min_difference = self.min_event_price - (100 - self.min_event_price) - self.max_loss
        max_differenct = self.max_event_price - (100 - self.max_event_price)

        #check max spread
        if abs(100 - price_1 - price_2) > self.max_loss: 
            logger.opt(colors=True).warning(f'{market["question"]} with spread <cyan>{abs(100 - price_1 - price_2)}c</cyan> is not suitable')
            return None
        
        #check min and max price difference 
        price_dif = abs(price_1 - price_2) 
        if price_dif >= min_difference and price_dif <= max_differenct:

            #select main token
            if price_1 > price_2: 
                main_token_id = tokens[0]
                hedge_token_id = tokens[1]
            else: 
                main_token_id = tokens[1]
                hedge_token_id = tokens[0]

            return {
                "question": market['question'],
                "clobTokenIds": market['clobTokenIds'],
                "main_token_id": main_token_id,
                "hedge_token_id": hedge_token_id,
                "main_price": price_1 if price_1>price_2 else price_2,
                "hedge_price": price_2 if price_1>price_2 else price_1
            }  

        else: 
            logger.opt(colors=True).warning(f'{market["question"]} with prices <cyan>{price_1}c</cyan> and <cyan>{price_2}c</cyan> is not suitable')
            return None

    async def market_search(self,):
        # Calculate max allowed end date
        max_end_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=self.market_resolve_days)

        for _ in range(ERR_ATTEMPTS):
            url = GAMMA_API + f"events?tag_slug={self.slug_of_events}&closed=false" 
            with Session() as session:
                with session.get(url) as response:
                    events = response.json()
                    if len(events) == 0: 
                        logger.error(f'Failed to get events from API for given {self.slug_of_events}, retrying in 10s...')
                        await async_sleep([10, 10])
                    else: 
                        break

        markets = []
        for event in events:
            # check event end date
            if event.get('endDate'):
                end_date = datetime.datetime.strptime(event['endDate'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
                if end_date > max_end_date:
                    logger.opt(colors=True).warning(f'{event["title"]} end date <c>{event["endDate"]}</c> is too far')
                    continue
                logger.opt(colors=True).success(f'{event["title"]} end date <c>{event["endDate"]}</c> is fine')
            else:
                continue

            for market in event['markets']:
                market = await self._process_single_market(market)
                if market:
                    markets.append(market)

        logger.info(f'Found overall {len(markets)} markets with the next event titles:')
        for market in markets:
            logger.opt(colors=True).info(f'Event - <c>{market["main_price"]}</c> vs. <c>{market["hedge_price"]}</c> - <m>{market["question"]}</m>')
        return markets

    async def set_market_list(self,):
        
        logger.info(f'Finding markets according to filters to open bets')
        self.market_list = await self.market_search()
        if len(self.market_list) == 0:
            logger.warning('No markets found according to filters')
            return False 
        else: 
            return True
        
    async def get_market(self,): 
        while True:
            if len(self.market_list) == 0:
                logger.info('No markets left according to filters, starting refresh...')
                self.set_market_list()
                sleep([50,100])
                continue 

            market = random.choice(self.market_list)
            res = await self._process_single_market(market)

            if not res: 
                logger.warning(f'Market {market["question"]} is no longer suitable for filters, trying again')
                del self.market_list[market]
                continue
            else: 
                return res


    def _distribute_amount(self, total_amt: float | int, num_parts:int, max_amount_per_wallet:float | int):
        if max_amount_per_wallet and total_amt > max_amount_per_wallet * num_parts:
            raise ValueError(f"Total amount {total_amt} too large to distribute among {num_parts} wallets with max {max_amount_per_wallet} per wallet")

        amounts = []
        remaining = total_amt
        power_factors = [pow(0.7, i) for i in range(num_parts)]
        total_factor = sum(power_factors)

        for i in range(num_parts - 1):
            proposed_amount = total_amt * (power_factors[i] / total_factor)
            if max_amount_per_wallet:
                amount = min(proposed_amount, max_amount_per_wallet)
            else:
                amount = proposed_amount
            amounts.append(amount)
            remaining -= amount

        # Handle the last amount
        if max_amount_per_wallet and remaining > max_amount_per_wallet:
            # If remaining amount exceeds max, we need to redistribute
            excess = remaining - max_amount_per_wallet
            amounts.append(max_amount_per_wallet)
            # Distribute excess back to other wallets that have room
            for i in range(len(amounts)):
                if excess <= 0:
                    break
                space_left = max_amount_per_wallet - amounts[i]
                additional = min(space_left, excess)
                amounts[i] += additional
                excess -= additional
            if excess > 0:
                raise ValueError("Cannot distribute amounts within max_amount_per_wallet constraint")
        else:
            amounts.append(remaining)

        return amounts
            
    async def _find_accounts(self, num_wallets:int, max_amount_per_wallet:float | None = None): 

        if num_wallets < 2:
            raise ValueError("Number of wallets must be at least 2")

        total_amount = random.uniform(TOTAL_AMOUNT[0], TOTAL_AMOUNT[1]) #сделать отдельное значение в конфиге
        _market_data = await self.get_market() 

        high_chance_token_id, low_chance_token_id = _market_data['main_token_id'], _market_data['hedge_token_id']
        high_chance_price, low_chance_price = _market_data['main_price'], _market_data['hedge_price']

        #calculate main and hedge amounts
        if BET_MORE_ON_HIGHEST_CHANCE:
            main_amount, hedge_amount = self.calculate_unbalanced_bets_amounts(total_amount, round(high_chance_price/100, 2), round(low_chance_price/100, 2))
        else:
            main_amount, hedge_amount, _= self.calculate_balanced_bets_amounts(total_amount, round(high_chance_price/100, 2), round(low_chance_price/100, 2))
        deviation = random.uniform(-BETS_DEVIATION_PERCENT/2, BETS_DEVIATION_PERCENT/2)/100

        main_amount = main_amount + main_amount * deviation
        hedge_amount = hedge_amount + hedge_amount * deviation

        # Calculate how many wallets to allocate for each side
        main_wallets = max(1, int(num_wallets * (main_amount / (main_amount + hedge_amount))))
        hedge_wallets = num_wallets - main_wallets

        # Distribute amounts
        main_amounts = self._distribute_amount(main_amount, main_wallets, max_amount_per_wallet)
        hedge_amounts = self._distribute_amount(hedge_amount, hedge_wallets, max_amount_per_wallet)

        # Find suitable accounts
        selected_accounts = []
        required_amounts = main_amounts + hedge_amounts

        random.shuffle(self.accounts)
        for amount in required_amounts:
            account_found = False
            for account in self.accounts[:]:  # Create a copy to iterate
                balance = get_erc20_balance(self.web3, account.funder, CHAINS_DATA['POLYGON']['USDC.e'])
                if balance >= amount:
                    selected_accounts.append(account)
                    self.accounts.remove(account)
                    account_found = True
                    break
            if not account_found:
                logger.warning('Not enough accounts with sufficient balance')
                return None

        # Prepare result
        result = {
            'question': _market_data['question'],
            'main_price': _market_data['main_price'],
            'main_accounts': selected_accounts[:main_wallets],
            'main_amounts': main_amounts,
            'hedge_price': _market_data['hedge_price'],
            'hedge_accounts': selected_accounts[main_wallets:],
            'hedge_amounts': hedge_amounts,
            'main_token_id': high_chance_token_id,
            'hedge_token_id': low_chance_token_id
        }

        return result
        
    def _ask_data(self,):
        self.slug_of_events = str(
            questionary.text("Input slug of events to search (ex. sports): \n").unsafe_ask()
        )
        self.slug_of_events = '' if len(self.slug_of_events) == 0 else self.slug_of_events.lower()

        self.market_resolve_days = str(
            questionary.text("Input max days till market resolves (default is 2): \n").unsafe_ask()
        )
        self.market_resolve_days = 2 if len(self.market_resolve_days) == 0 else int(self.market_resolve_days)

        self.acc_qnty_per_fork = str(
            questionary.text("Input amount of accounts per fork (default is 2 - 4): \n").unsafe_ask()
        )
        self.acc_qnty_per_fork = [2, 4] if len(self.acc_qnty_per_fork) == 0 else [int(x) for x in self.acc_qnty_per_fork.split('-')]

        self.max_amount_per_wallet = str(
            questionary.text("Input max amount per wallet (default is 35$): \n").unsafe_ask()
        )
        self.max_amount_per_wallet = 35 if len(self.max_amount_per_wallet) == 0 else float(self.max_amount_per_wallet)

        self.min_liquidity = self.acc_qnty_per_fork[1] * self.max_amount_per_wallet

        self.max_loss = str(
            questionary.text("Input max spread in cents (default is 2c): \n").unsafe_ask()
        )
        self.max_loss = 2 if len(self.max_loss) == 0 else float(self.max_loss)

        self.min_event_price = str(
            questionary.text("Min price for high chance event (default is 70c): \n").unsafe_ask()
        )
        self.min_event_price = 70 if len(self.min_event_price) == 0 else float(self.min_event_price)

        self.max_event_price = str(
            questionary.text("Max price for high chance event (default is 90c): \n").unsafe_ask()
        )
        self.max_event_price = 90 if len(self.max_event_price) == 0 else float(self.max_event_price)

    async def run_forks(self, ):

        if not await self.set_market_list():
            return 
        while True:

            if len(self.accounts) < self.acc_qnty_per_fork[0]:
                logger.warning(f'Not enough accounts ({len(self.accounts)})left to open forks')
                return
            if len(self.accounts) < self.acc_qnty_per_fork[1]:
                acc_qnty = len(self.accounts)
            else:
                acc_qnty = random.randrange(self.acc_qnty_per_fork[0], self.acc_qnty_per_fork[1])

            data = await self._find_accounts(acc_qnty, self.max_amount_per_wallet)
            if not data:
                logger.warning('No accounts with enough balance to open forks')
                return

            main_accounts = data['main_accounts']
            main_amounts = data['main_amounts']
            hedge_accounts = data['hedge_accounts']
            hedge_amounts = data['hedge_amounts']
            main_token_id = data['main_token_id']
            hedge_token_id = data['hedge_token_id']

            # Prepare all accounts and their orders
            all_orders = [
                (account, amount, main_token_id, 'main') 
                for account, amount in zip(main_accounts, main_amounts)
            ] + [
                (account, amount, hedge_token_id, 'hedge') 
                for account, amount in zip(hedge_accounts, hedge_amounts)
            ]
            
            # Log all accounts
            logger.opt(colors= True).info(f'Starting fork on event <m>{data["question"]}</m>')
            logger.opt(colors=True).info(f'Main amount to be spent: <c>{sum(main_amounts)}$</c>')
            logger.opt(colors=True).info(f'Hedge amount to be spent: <m>{sum(hedge_amounts)}$</m>')
            main_addresses = [f'<cyan><bold>{acc.address}</bold></cyan>' for acc in main_accounts]
            hedge_addresses = [f'<magenta><bold>{acc.address}</bold></magenta>' for acc in hedge_accounts]
            logger.opt(colors=True).info(f'Main accounts: {" | ".join(main_addresses)}')
            logger.opt(colors=True).info(f'Hedge accounts: {" | ".join(hedge_addresses)}')

            # Randomize order execution
            random.shuffle(all_orders)
            
            # Execute all orders
            successful_orders = []
            
            for account, amount, token_id, side in all_orders:
                order = None
                current_account = account
                
                # Try with initial account
                order = current_account.market_buy(token_id, amount)
                
                # If failed, try to find a replacement account
                if not order:
                    logger.warning(f'{current_account.address} - {side.capitalize()} order failed to fill. Trying to find replacement...')
                    
                    # Try to find an account with sufficient balance
                    for potential_account in self.accounts[:]:
                        balance = get_erc20_balance(self.web3, potential_account.funder, CHAINS_DATA['POLYGON']['USDC.e'])
                        if balance >= amount:
                            current_account = potential_account
                            self.accounts.remove(potential_account)
                            order = current_account.market_buy(token_id, amount)
                            if order:
                                logger.info(f'Successfully replaced with account {current_account.address}')
                                break
                
                # If still no order after trying replacement
                if not order:
                    logger.warning('Failed to find replacement account. Closing all active positions in the group')
                    
                    # Close all successful positions
                    for prev_account, _, prev_token_id, _ in successful_orders:
                        if not prev_account.sell_all_positions_on_market(prev_token_id):
                            logger.warning(f'{prev_account.address} - Failed to close positions, please check manually')
                        sleep(SLEEP_BETWEEN_WALLETS_IN_FORK)
                    
                    break  # Exit after closing positions
                
                successful_orders.append((current_account, amount, token_id, side))
                sleep(SLEEP_BETWEEN_WALLETS_IN_FORK)

            sleep(SLEEP_BETWEEN_FORKS)








        


        

