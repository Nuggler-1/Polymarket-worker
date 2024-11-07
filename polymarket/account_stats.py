from utils.utils import async_error_handler, error_handler, get_erc20_balance
from vars import CHAINS_DATA
from config import RPC

from loguru import logger 
from web3 import Web3 
from aiohttp import ClientSession
from rich.table import Table
from rich.text import Text


class WalletStats():

    def __init__(self, account_address: str, proxy_address: str, proxy: str | None = None): 

        self.account_address = account_address
        self.proxy_address = proxy_address
        self.proxy = proxy


    @async_error_handler('Failed to parse volume')
    async def _check_volume(self): 

        volume_url = f'https://lb-api.polymarket.com/volume?window=all&limit=1&address={self.proxy_address}'

        async with ClientSession() as session: 
            async with session.get(volume_url, proxy=self.proxy) as response: 
                resp_json = await response.json()

        volume = resp_json[0]['amount']
        return round(float(volume), 2)
    

    @error_handler('Failed to check balance')
    async def _check_balance(self): 

        web3 = Web3(Web3.HTTPProvider(RPC['POLYGON']))
        balance = get_erc20_balance(web3, self.proxy_address,CHAINS_DATA['POLYGON']['USDC.e'])

        url_balance = f'https://data-api.polymarket.com/value?user={self.proxy_address}'
        async with ClientSession() as session: 
            async with session.get(url_balance, proxy=self.proxy) as response: 
                resp_json = await response.json()

        balance = resp_json[0]['value'] + balance
        return round(float(balance), 2) 
    
    @async_error_handler('Failed to check positions')
    async def _check_positions(self): 

        positions_url = f'https://data-api.polymarket.com/positions?user={self.proxy_address}&sortBy=CURRENT&sortDirection=DESC&sizeThreshold=.1&limit=50&offset=0'
        positions = []

        async with ClientSession() as session: 
            async with session.get(positions_url, proxy=self.proxy) as response: 
                resp_json = await response.json()

        if len(resp_json) == 0: 
            return 0
        
        for position in resp_json: 
            if float(position['currentValue']) > 0:
                positions.append(
                    {
                    'title': position['title'],
                    'side': position['outcome'],
                    'value': round(float(position['initialValue']), 2),
                    'current value': round(float(position['currentValue']), 2),
                    'pnl': round(float(position['cashPnl']),2)
                }
            )

        return positions 
    
    @async_error_handler('Failed to parse profit')
    async def _check_total_profit(self): 

        profit_url = f'https://lb-api.polymarket.com/profit?window=all&limit=1&address={self.proxy_address}'

        async with ClientSession() as session: 
            async with session.get(profit_url, proxy=self.proxy) as response: 
                resp_json = await response.json()

        profit = resp_json[0]['amount']
        return round(float(profit), 2)
    
    @async_error_handler('Failed to parse traded markets')
    async def _check_markets_traded(self): 

        traded_url = f'https://lb-api.polymarket.com/traded?user={self.proxy_address}'

        
        async with ClientSession() as session: 
            async with session.get(traded_url, proxy=self.proxy) as response: 
                resp_json = await response.json()
        amount = resp_json['traded']
        return amount
    
    async_error_handler('Failed to parse nickname')
    async def _get_nickname(self): 

        url = f'https://polymarket.com/api/profile/userData?address={self.proxy_address}'

        async with ClientSession() as session: 
            async with session.get(url, proxy=self.proxy) as response: 
                resp_json = await response.json()

        return resp_json['name']
    
    async def display_stats(self, table: Table): 

        nickname = await self._get_nickname()
        volume = await self._check_volume()
        balance = await self._check_balance()
        positions = await self._check_positions()
        profit = await self._check_total_profit()
        #markets_traded = await self._check_markets_traded()

        
        logger.opt(colors=True).info(f'STATS FOR <cyan>{self.account_address}</cyan>')
        print()
        logger.opt(colors=True).info(f'Polymarket address: <green>{self.proxy_address}</green>')
        logger.opt(colors=True).info(f'Nickname: {nickname}')
        logger.opt(colors=True).info(f'Balance: {balance}') 
        logger.opt(colors=True).info(f'Volume: {volume}')
        total_profit_msg = f'Total profit: <green>{profit}</green>' if profit > 0 else f'Total profit: <red>{profit}</red>'
        logger.opt(colors=True).info(total_profit_msg)
        #logger.opt(colors=True).info(f'Markets traded: {markets_traded}')
       
        # Add rows with colored specific values
        table.add_row(
            Text(self.account_address),
            Text(self.proxy_address, style='cyan'),
            Text(nickname),
            Text(str(balance)),
            Text(str(volume)),
            Text(str(profit), style='green' if profit > 0 else 'red'),
            Text(str(len(positions)) if positions != 0 else '0')
        )

        return table

    @async_error_handler('Failed to display positions')
    async def display_positions(self): 
        
        positions = await self._check_positions()
        if positions != 0:
            logger.opt(colors=True).info(f'<green>{self.account_address}</green> - <cyan>{self.proxy_address}</cyan> - POSITIONS:')
            for position in positions: 
                print()
                logger.opt(colors=True).info(f'{position["title"]}')
                side_msg = f'Side: <green>{position["side"]}</green>' if position["side"] == 'Yes' else f'Side: <red>{position["side"]}</red>'
                logger.opt(colors=True).info(side_msg)  
                logger.opt(colors=True).info(f'Value: {position["value"]}')
                logger.opt(colors=True).info(f'Current value: {position["current value"]}')
                pnl_msg = f'PnL: <green>{position["pnl"]}</green>' if position["pnl"] > 0 else f'PnL: <red>{position["pnl"]}</red>'
                logger.opt(colors=True).info(pnl_msg)
