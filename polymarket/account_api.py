from eth_account import Account as EthAccount
from eth_account.messages import encode_defunct
from aiohttp import ClientSession
from loguru import logger
from math import ceil
from playwright.async_api import async_playwright
import asyncio

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, OpenOrderParams,BalanceAllowanceParams, AssetType, TradeParams
from py_clob_client.order_builder.constants import BUY, SELL
from .account_ui import Account as AccountUI


from utils.utils import error_handler, round_up, round_down, async_sleep, get_proxy
from .constants import HOST, CHAIN_ID
import requests 

from config import IGNORE_ASK_SIZE

#добавить прокси в клиент 

"""
аккаунт должен:

- покупать лимитку 
- продавать лимитку 
"""

class Account(): 

    def __init__(self,private_key, funder, proxy=None): 

        """
        Private_key - is original MM private key
        Funder is polymarket proxy address!

        proxies = {
            "http": "http://username:password@your_proxy:port",
            "https": "https://username:password@your_proxy:port"
        }
        """
        
        host = HOST
        chain_id = CHAIN_ID
        self.proxy = proxy

        self._private_key = private_key
        self.funder = funder
        assert len(funder) == 32, 'check user_data/polymarket_addresses.txt'
        self.address = EthAccount.from_key(private_key).address

        self.client = ClobClient(host, chain_id= chain_id, key = private_key,  signature_type=2, funder=funder, proxy=proxy)
        self.create_client()

    @error_handler('creating client')
    def create_client(self): 
        self.client.set_api_creds(self.client.create_or_derive_api_creds())

    @error_handler('getting market price', retries=1)
    def _get_market_price(self, token_id:str, side:str, size:float) :   
        """
        returns price in dollars
        size in dollars!
        """ 
        
        resp = self.client.get_order_book(token_id)

        if side == 'BUY': 
            for ask in reversed(resp.asks): 
                if float(ask.price) * float(ask.size) >= size: 
                    return float(ask.price)
        
        if side == 'SELL': 
            for bid in reversed(resp.bids): 
                if float(bid.price) * float(bid.size) >= size: 
                    return float(bid.price)
                
        raise Exception('No liquidity to make market order')
    
    @staticmethod
    @error_handler('getting token ids')
    def _get_token_ids(market_id: str):
        """
        returns dict with token ids for YES and NO
        """
        
        url = f'https://clob.polymarket.com/markets/{market_id}'
        yes_id = None 
        no_id = None 
        with requests.Session() as session:
            response = session.get(url)
            try:    
                tokens = response.json()['tokens']
                for token in tokens: 
                    if token['outcome'] == 'Yes': 
                        yes_id = token['token_id']
                    if token['outcome'] == 'No':
                        no_id = token['token_id']
            except:
                logger.warning(f'No token ids found for market {market_id}')
                return None

        if not yes_id or not no_id:
            return None
        else:
            return {
                'YES': yes_id,
                'NO': no_id
            }
        
    def get_position_size(self, token_id): 
        """
        returns size in shares
        """
        url = f'https://data-api.polymarket.com/positions?user={self.funder}&sizeThreshold=.1&limit=50&offset=0&sortBy=CURRENT&sortDirection=DESC'
        with requests.Session() as session: 
            response = session.get(url, proxies=self.proxy)
            data = response.json()

        for position in data: 
            if position['asset'] == token_id: 
                return position['size']
            
        return 0
    
    @error_handler('getting market name')
    def get_market_name(self, market_id): 
        url = 'https://clob.polymarket.com/markets/'

        with requests.Session() as session:
            resp = session.get(url+market_id)
            resp_json = resp.json()
            return resp_json['question']
        
    async def _set_approves(self,): 

        account = AccountUI(self._private_key, proxy = get_proxy(self._private_key, mode = 'dict'))

        async with async_playwright() as playwright: 
            browser = await account._init_browser(playwright)
            await async_sleep([3,5])
            page = await account.preapre_page(browser)

            await account.approve_pending_deposit(browser, page)
            await async_sleep([5,10])
            await account.approve_tokens(browser, page)

    @error_handler('buy limit', retries=1)
    def limit_buy(self,token_id:str, price: float | int | str, size: float | int |str, order_type: OrderType = OrderType.GTC):
        """
        price in cents!
        
        """
   
        if order_type == OrderType.FOK: 
            price=round_up(float(price)/100, 2)
        else: 
            price=round(float(price)/100, 3)

        size=float(size)
        logger.info(f'{self.address} - placing buy order for {size} shares at {price*100} cents')
        order_args = OrderArgs(
            price=price,
            size=round(size, 2),
            side=BUY,
            token_id=token_id
        )

        signed_order = self.client.create_order(order_args)

        ## Good Till Cancel Order
        resp = self.client.post_order(signed_order, order_type)
        
        return resp
        
    
    @error_handler('sell limit', retries=1)
    def limit_sell(self, token_id:str, price: float | int | str, size: float | int |str, order_type: OrderType = OrderType.GTC): 
        """
        price in cents!

        """

        price=round(float(price)/100, 3)
        size=round_down(float(size), 2)
        logger.info(f'{self.address} - placing sell order for {size} shares at {price*100} cents')
        order_args = OrderArgs(
            price=price,
            size=size,
            side=SELL,
            token_id=token_id
        )

        signed_order = self.client.create_order(order_args)

        ## Good Till Cancel Order
        resp = self.client.post_order(signed_order, order_type)
        
        return resp


            
    
    @error_handler('market order')
    def market_sell(self, token_id:str, size:float): 
        """
        size in dollars!

        """
        price = self._get_market_price(token_id, 'SELL', size)
        size = ceil(size/price)
  
        ## fill or kill order
        order = self.limit_sell(token_id, price * 100, size)
        if order['status'] == 'matched':
            logger.success(f'{self.address} - Market order filled')
            return 1
        else: 
            raise Exception('Market order failed to fill')
        
    @error_handler('market order')
    def market_buy(self, token_id:str, size:float): 
        """
        size in dollars!

        """
        price = self._get_market_price(token_id, 'BUY', size)
        size = ceil(size/price)
  
        ## fill or kill order
        order = self.limit_buy(token_id, price*100, size, order_type = OrderType.FOK)
        if order['status'] == 'matched':
            logger.success(f'{self.address} - Market order filled')
            return 1
        else: 
            raise Exception('Market order failed to fill')



    @error_handler('checking active oreders on market')
    def get_active_orders(self, market_id:str):
        """
        returns list of active orders
        """
        resp = self.client.get_orders(
            OpenOrderParams(
                market=market_id,
            )
        )
        return resp

    @error_handler('closing all active orders')
    def close_active_orders(self,):
        resp = self.client.cancel_all()
        return resp
    
    @error_handler('closing specific order')
    def close_specific_order(self, order_id:str):
        resp = self.client.cancel(order_id=order_id)
        return resp

    @error_handler('checking order book')
    def check_order_book_empty(self, ask_price: float | int , token_id:str): 
        """
        ask_price - in cents!

        Bid - должен быть пустой полностью
        Ask - должен быть пустой ниже определенной цены
        """
        resp = self.client.get_order_book(token_id)

        if len(resp.bids) > 0: 
            logger.warning('Someone else is sitting in Bids!')
            return False
        
        if float(resp.asks[-1].price) <= ask_price/100 and float(resp.asks[-1].price) * float(resp.asks[-1].size) > IGNORE_ASK_SIZE:
            logger.warning('Someone else is sitting in Asks!')
            return False
        
        logger.info('Order book is empty - good to go')
        return True
    
    def get_max_buy_size(self, price: float | int , token_id:str): 
        """
        returns available orderbook liquidity (in dollars) for given price
        """
        resp = self.client.get_order_book(token_id)
        
        if float(resp.asks[-1].price) > price/100:
            logger.warning('no liquidity to buy')
            return 0
        else:
            return float(resp.asks[-1].size)
    
    @error_handler('selling all positions on market')
    def sell_all_positions_on_market(self, token_ids:dict): 

        if not token_ids:
            logger.warning(f'No positions found in market ')
            return 1
        
        for token_id in list(token_ids.values()): 
            size = self.get_position_size(token_id)
            price = self._get_market_price(token_id, SELL, size)
            assert self.limit_sell(token_id, price, size, order_type = OrderType.FOK)['status'] == 'matched', 'Failed to fill order'
        
        return 1
            
    @error_handler('dropping all positions')
    def drop_all_positions(self, ): 

        logger.info(f'{self.address} - Dropping all positions')
        url = f'https://data-api.polymarket.com/positions?user={self.funder}&sizeThreshold=.1&limit=50&offset=0&sortBy=CURRENT&sortDirection=DESC'
        with requests.Session() as session: 
            response = session.get(url, proxies=self.proxy)
            data = response.json()

        if len(data) == 0: 
            logger.info(f'{self.address} - No positions to drop')
            return 1

        for position in data: 
            self.close_active_orders()
            token_id = position['asset']
            size = position['size']
            price = position['curPrice']

            if position['curPrice'] * size > 0.1:
                logger.opt(colors=True).info(f'{self.address} - Dropping position <red>{position["title"]}</red> with size {size}')
                price = self._get_market_price(token_id, 'SELL', size*price)
                if price == 0: 
                    continue
                assert self.limit_sell(token_id, price*100, size)['status'] == 'matched', 'Failed to fill order'
                logger.success(f'{self.address} - order filled')
            else: 
                logger.opt(colors=True).warning(f'{self.address} - Skipping position <red>{position["title"]}</red> with size {size} because it is too small or the market has ended')
        
        logger.info(f'{self.address} - No positions left')

        return 1
    
    @error_handler('getting last trade')
    def get_last_trade_size(self, market_id:str):
        
        resp = self.client.get_trades(
            TradeParams(
                maker_address=self.funder,
                market=market_id,
            ),
        )

        if len(resp) == 0: 
            logger.warning('No trades found')
            return 0
        
        return int(resp[0]['size'])
        

        

            





        