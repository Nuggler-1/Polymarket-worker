from utils.utils import send_tx, send_request, get_contract, intToDecimal, async_error_handler
from vars import ERC20_ABI, CHAIN_ID_TO_NAME
from web3 import Web3 
from aiohttp import ClientSession

from config import RPC
import random

class RelayAccount(): 

    def __init__(self,private_key:str): 

        self.base_url = 'https://api.relay.link/'
        self.private_key = private_key

    async_error_handler('failed to get relay bridge data',)
    async def _quote(self,web3, account, amount,chain_to, chain_from, token_to, token_from, recipient):
    
        contract = get_contract(web3, account.address,ERC20_ABI)
        balance = contract.functions.balanceOf(account.address)

        if amount: 
            amount = balance * random.uniform(amount[0], amount[1])/100 
        else: 
            amount = balance 

        async with ClientSession() as session: 
            data = {

                'amount': amount,
                'destinationChainId': chain_to,
                'destinationCurrency': token_to,
                'originChainId': chain_from,
                'originCurrency': token_from,
                'recipient': recipient,
                'refferer': 'relay.link/swap',
                'tradeType': 'EXACT_INPUT',
                'useExternalLiquidity': False,
                'user': account.address

            }
            async with session.get(self.base_url+'quote', json= data) as resp: 
                resp_json = await resp.json()
                tx = resp_json['steps']['items'][0]['data']
                return tx 
    
    @async_error_handler('token bridge')
    async def bridge_tokens(self,chain_from_id:int, chain_to_id:int, token_from:str, token_to:str, amount: list | None , recipient: str | None):
        """
        amount None = Full balance
        amount list = [1, 100] % random percent of balance

        recipient = address | None = self address
        """
        web3 = Web3(Web3.HTTPProvider(RPC[CHAIN_ID_TO_NAME[chain_from_id]]))
        account = web3.eth.account.from_key(self.private_key)

        if not recipient: 
            recipient = account.address

        
        tx = await self._quote(web3, account, amount, chain_to_id, chain_from_id, token_to, token_from, recipient)
        assert tx != 0, 'failed to quote'
        sent_tx = send_tx(web3, account, tx, value=tx['value'])
        return sent_tx 


    


