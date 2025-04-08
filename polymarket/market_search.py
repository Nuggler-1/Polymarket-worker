
import asyncio
import re

from loguru import logger
from aiohttp import ClientSession

from utils.utils import async_error_handler, get_random_proxy

class Search():
    
    def __init__(self,):

        self.market_list_url ="https://gamma-api.polymarket.com/events?limit=20&active=true&archived=false&closed=false&order=volume24hr&ascending=false&offset="
        self.order_book_url = f'https://clob.polymarket.com/books/'
        self.events_to_check = None
        self.min_liquidity = None
        self.max_price_sum = None
        self.max_price_difference = None

    @staticmethod 
    def calculate_unbalanced_bets_amounts(total_amount: float | int, price_a: float | int, price_b: float | int):
        """
        prices and total amount passed in dollars!!!!
        price_a is price of the high conviction bet (the winning one)
        price_b is a price of the less conviction bet
        """

        bet_a = total_amount * price_a
        bet_b = total_amount - bet_a 
        
        return bet_a, bet_b



    @staticmethod
    def calculate_balanced_bets_amounts(total_amount, price_a, price_b):
        """
        returns amount for each bet and total return of bets based on prices and total amount passed in DOLLARS
        """
        bet_a = total_amount/ (1 + price_b/price_a)
        bet_b = total_amount/((price_a+price_b)/price_b)
        
        return_of_bet = bet_a * (1/price_a) - total_amount
        
        return bet_a, bet_b, return_of_bet


    def _chunk_dict(self,data, chunk_size):
        # Method 1: Using list comprehension with items()
        items = list(data.items())
        return [{k: v for k, v in items[i:i + chunk_size]} 
                for i in range(0, len(items), chunk_size)]

    async def _process_market_prices(self,name:str, tokens:list):

        try: 
            price_1 =  await self._get_market_price(tokens[0],  self.min_liquidity)       
            price_2 =  await self._get_market_price(tokens[1],  self.min_liquidity)
            price_sum = price_1 + price_2

            logger.opt(colors=True).info(f'LOSS <magenta>{round((1-price_sum)*100, 3)}%</magenta> - YES <cyan>{price_1:.3f}$</cyan> - NO <cyan>{price_2:.3f}$</cyan> - {name}')

        except Exception as e: 
            logger.opt(colors=True).warning(f'Error getting market price for <cyan>{name}</cyan>: {str(e)}')
            return None

        if price_sum <= self.max_price_sum and abs(price_1 - price_2) <= self.max_price_difference and price_sum > 0.9:
            return {name: {tokens[0]: price_1, tokens[1]: price_2}}
        else: 
            return None

    @async_error_handler('finding markets', retries=1)
    async def find_markets(self,amount_of_events:int, min_liquidity:float, max_loss:float, max_price_difference:float): 
        """
        min_liquidity - minimum liquidity to make a bet in $

        max_loss - maximum loss in %

        max_price_difference - maximum price difference in cents

        returns dict with markets and tokens prices
        {'market_name': {'token_1': price_1, 'token_2': price_2}}
        """

        self.events_to_check = amount_of_events
        self.min_liquidity = min_liquidity
        self.max_price_sum = 1+max_loss/100
        self.max_price_difference = max_price_difference/100

        opposing_tokens = await self._find_opposing_tokens()
        market_chunks = self._chunk_dict(opposing_tokens, 20)
        
        good_markets = {}
        for chunk in market_chunks: 
            tasks = []
            for name, tokens in chunk.items(): 
                tasks.append(asyncio.create_task(self._process_market_prices(name, tokens)))
            results = await asyncio.gather(*tasks)
            for result in results: 
                if result: 
                    good_markets.update(result)

        return good_markets

    @async_error_handler('getting market ids', retries=1)
    async def _find_opposing_tokens(self,):
        
        opposing_tokens={}
        for i in range(0, self.events_to_check, 10):

            logger.info(f'getting market ids for {i+1} - {i+10} events')
            async with ClientSession()as session:
                async with session.get(self.market_list_url+str(i)) as resp:
                    data = await resp.json()
                    #await asyncio.sleep(0.2)

            for event in data: 
                markets = event['markets']
                for market in markets: 
                    try:
                        
                        clob_id = market['clobTokenIds']
                        matches = re.findall(r'\d+', clob_id)
                        if matches: 
                            
                            opposing_tokens[market['question']] = matches
                    except : 
                        pass

        return opposing_tokens

    @async_error_handler('getting market price', retries=2)
    async def _get_market_price(self,token_id:str, size:float) :   
        """
        returns price in dollars
        size in dollars!
        """ 
        proxy = get_random_proxy()
        json = [{'token_id':token_id}]
        async with ClientSession() as session:
            async with session.get(self.order_book_url, json = json, proxy = proxy) as resp:
                assert resp.status == 200, f'Error getting market price for {token_id}'
                response_data = await resp.json()
                #logger.success(response_data[0]['market'])
                
        try: 
            for ask in reversed(response_data[0]['asks']): 
                if float(ask['price']) * float(ask['size']) >= size: 
                    return float(ask['price'])
        except IndexError: 
            logger.warning(f'No asks found {response_data}')

        return 0

