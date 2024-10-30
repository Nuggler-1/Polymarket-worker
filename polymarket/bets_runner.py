
from config import TOTAL_AMOUNT, RPC, MARKET_BETS, PERCENT_OF_BALANCE_TO_BET, WALLET_SLEEP
from vars import CHAINS_DATA
from utils.utils import get_erc20_balance, error_handler, get_deposit_wallet, sleep, get_proxy, split_list_into_n_chunks
from utils.constants import DEFAULT_POLYMARKET_WALLETS, DEFAULT_PROXIES
import random
from web3 import Web3
from loguru import logger
from .account_api import Account as AccountAPI

class BetsRunner():

    def __init__(self, private_keys: list[str]):
        self.private_keys = private_keys
        self.accounts = []
        self.web3 = Web3(Web3.HTTPProvider(RPC['POLYGON']))
        for key in private_keys:
            self.accounts.append(AccountAPI(key, funder = get_deposit_wallet(key, deposit_addresses=DEFAULT_POLYMARKET_WALLETS), proxy = get_proxy(key) ) )
        
    def run_bets(self, ):

        random.shuffle(self.accounts)
        accounts_chunks = split_list_into_n_chunks(self.accounts, len(MARKET_BETS))

        for account_chunk, market_bet in zip(accounts_chunks, MARKET_BETS): 

            side = market_bet[1]
            market_id = market_bet[0]
            for account in account_chunk:
                
                balance = get_erc20_balance(self.web3, account.funder, CHAINS_DATA['POLYGON']['USDC.e'])
                amount_to_bet = round(balance * random.uniform(PERCENT_OF_BALANCE_TO_BET[0], PERCENT_OF_BALANCE_TO_BET[1]) / 100, random.randint(1, 2)) 

                token_ids = AccountAPI._get_token_ids(market_id)
                if not token_ids:
                    logger.warning(f'No token ids found for market {market_id}')
                    continue

                market_name = account.get_market_name(market_id)
                side_token = token_ids[side] 
                side_colored = f'<green>{side}</green>' if side == 'YES' else f'<red>{side}</red>'
                logger.opt(colors=True).info(f'{account.address} - placing <cyan>{amount_to_bet}$</cyan> bet on <cyan>{market_name}</cyan> - {side_colored}')
                order = account.market_buy(side_token, amount_to_bet)

                if not order: 
                    logger.warning(f'{account.address} - Order failed to fill')
                    account.close_active_orders()
                    continue 

                sleep(WALLET_SLEEP)


