import random
import questionary
import asyncio
from web3 import Web3
from loguru import logger
from .account_api import Account as AccountAPI

from config import TOTAL_AMOUNT, RPC,BETS_DEVIATION_PERCENT, SLEEP_BETWEEN_WALLETS_IN_FORK, SLEEP_BETWEEN_FORKS
from vars import CHAINS_DATA
from utils.constants import DEFAULT_POLYMARKET_WALLETS
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
        #self.set_market_list()

    async def set_market_list(self,):

        logger.info(f'Finding markets according to filters to open bets')
        self.market_list = await self.find_markets(self.events_to_check, self.min_liquidity, self.max_loss, self.max_price_difference)
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
                name = list(res.keys())[0]
                tokens = list(res[name].keys())
                res = {
                    "question": name,
                    "main_token_id": tokens[0],
                    "hedge_token_id": tokens[1],
                    "main_price": res[name][tokens[0]],
                    "hedge_price": res[name][tokens[1]],
                }  
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
        main_amount, hedge_amount, _ = self.calculate_balanced_bets_amounts(total_amount, high_chance_price, low_chance_price)
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
        amount_of_events = str(
            questionary.text("Input amount of events to check (default is 20): \n").unsafe_ask()
        )
        amount_of_events = 20 if len(amount_of_events) == 0 else int(amount_of_events)

        self.acc_qnty_per_fork = str(
            questionary.text("Input amount of accounts per fork (default is 2 - 4): \n").unsafe_ask()
        )
        self.acc_qnty_per_fork = [2, 4] if len(self.acc_qnty_per_fork) == 0 else [int(x) for x in self.acc_qnty_per_fork.split('-')]

        self.max_amount_per_wallet = str(
            questionary.text("Input max amount per wallet (default is 35$): \n").unsafe_ask()
        )
        self.max_amount_per_wallet = 35 if len(self.max_amount_per_wallet) == 0 else float(self.max_amount_per_wallet)

        min_liquidity = str(
            questionary.text("Input min liquidity in market orderbook (default is 150$): \n").unsafe_ask()
        )
        min_liquidity = 150 if len(min_liquidity) == 0 else float(min_liquidity)

        max_loss = str(
            questionary.text("Input max loss in % (default is 5%): \n").unsafe_ask()
        )
        max_loss = 5 if len(max_loss) == 0 else float(max_loss) 

        max_price_difference = str(
            questionary.text("Input max price difference in cents [2 - 98] (default is 20 e.g. max difference of bets is 60 to 40): \n").unsafe_ask()
        )
        max_price_difference = 20 if len(max_price_difference) == 0 else float(max_price_difference) 

        return amount_of_events, min_liquidity, max_loss, max_price_difference
    
    
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








        


        

