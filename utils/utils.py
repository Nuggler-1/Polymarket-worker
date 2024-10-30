import random
import sys
import time
from loguru import logger
from eth_account import Account
from web3 import Web3
import requests
import math
import os
from termcolor import cprint
import colorama
from colorama import Fore
from config import *
from vars import * 
import asyncio
from math import ceil
import utils.eip1559 as eip1559
import json
from stringtools.generators import Nick

from .constants import *

import re
import shutil

def generate_name(length:list[int, int], numbers:list[int,int], disable_numbers:bool = False):
    n  = Nick()
    n.set_length(random.randrange(length[0],length[1]))
    name = n.generate()
    
    if bool(random.getrandbits(1)) and not disable_numbers: 
        name = name+str(random.randrange(numbers[0],numbers[1]))
    
    return name.lower()


def error_handler(error_msg, retries = ERR_ATTEMPTS):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(0, retries):
                try: 
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"{error_msg}: {str(e)}")
                    logger.info(f'Retrying in 10 sec. Attempts left: {ERR_ATTEMPTS-i}')
                    time.sleep(10)
                    if i == ERR_ATTEMPTS-1: 
                        return 0
        return wrapper
    return decorator

def async_error_handler(error_msg, retries=ERR_ATTEMPTS):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for i in range(0, retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"{error_msg}: {str(e)}")
                    if i == retries - 1:
                        return 0
                    logger.info(f"Retrying in 10 sec. Attempts left: {retries-i-1}")
                    await asyncio.sleep(10)
                    
        return wrapper
    return decorator

@error_handler('convert to usd value')
def tokens_to_usd(token_gecko_id, token_amount): 

    url = f'https://api.coingecko.com/api/v3/coins/{token_gecko_id}?localization=false&tickers=false&community_data=false&developer_data=false&sparkline=false'
    response = send_request(True, url)

    assert response.status_code == 200, 'failed to get token price'

    price = response.json()['market_data']['current_price']['usd']

    overall_sum = token_amount * price

    return overall_sum 

def clear_file(file):
    file_to_clear = open(file,'w', encoding="utf-8")
    file_to_clear.close()

def write_to_file(file, result):
    with open(file, "a", encoding="utf-8") as file:
        file.write(str(result) + '\n')


@error_handler('wait balance')
def wait_balance(web3, account): 

    for i in range(0, int(MAX_BALANCE_WAIT/10)):
        logger.info(f'{account.address}: waiting for balance to appear in {CHAIN_ID_TO_NAME[web3.eth.chain_id]}')
        balance = web3.eth.get_balance(account.address)
        if balance > 0: 
            logger.success(f'{account.address}: balance updated')
            return 
        time.sleep(10)

    logger.error(f'{account.address}: balance waiting time exceeded')

def wait_erc_balance(web3, account, token,  min_balance = 1): 

    contract = web3.eth.contract(address = token, abi = ERC20_ABI,)
    decimals = contract.functions.decimals().call()
    min_balance = intToDecimal(min_balance, decimals)

    for i in range(0, int(MAX_BALANCE_WAIT/10)):
        logger.info(f'{account.address}: waiting for token balance to appear in {CHAIN_ID_TO_NAME[web3.eth.chain_id]}')
        balance = contract.functions.balanceOf(account.address).call()
        
        if balance >= min_balance: 
            logger.success(f'{account.address}: balance updated')
            return 
        time.sleep(10)

    logger.error(f'{account.address}: balance waiting time exceeded')

error_handler('gas waiter')
def wait_for_gas(web3): 

    while True: 
        
        try: 
            if web3.eth.gas_price < Web3.to_wei(MAX_GAS_PRICE, 'gwei'): 
                return  
            logger.info(f'Waiting for gas to drop. Current {Web3.from_wei(web3.eth.gas_price, "gwei")}')

        except: 
            pass 

        time.sleep(20)

def split_list_into_n_chunks(lst, n):
  
  size = ceil(len(lst) / n)

  return list(
    map(lambda x: lst[x * size:x * size + size],
    list(range(n)))
  )

def split_list_into_sized_chunks(lst, chunk_size):

    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def pairs_from_list(lst):
    # Handle empty list or list with odd number of elements
    if not lst or len(lst) % 2:
        raise ValueError("List must have even number of elements")
        
    # Use range with step=2 to get every other element
    for i in range(0, len(lst)-1, 2):
        yield lst[i], lst[i+1]


def send_tx(web3, account, tx, value=0, return_hash: bool = False):

    try: 
        tx['to'] = Web3.to_checksum_address(tx['to'])
        tx['from'] = Web3.to_checksum_address(tx['from'])
        tx ['value'] = int(value)
    
        gas = web3.eth.estimate_gas(tx)
        nonce = web3.eth.get_transaction_count(account.address)

        tx['chainId'] = web3.eth.chain_id
        tx ['nonce'] = nonce
        tx ['gas'] = gas 

        tx = eip1559.get_gas_prices(CHAIN_ID_TO_NAME[web3.eth.chain_id], tx)

        signed_tx = account.sign_transaction(tx)
        hash_tx = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logger.info(f'{account.address}: Transaction was sent')
        tx_passed = check_transaction(web3, hash_tx)

        if return_hash == False:
            return tx_passed
        else: 
            return hash_tx.hex()
        
    except Exception as e: 

        logger.error(f'{account.address}: {str(e)}')
        return 0

def build_and_send_tx(web3, account, tx, value = 0, return_hash: bool = False, custom_gas = 0, custom_gasprice=0):
    
    try:
        gas = tx.estimate_gas({'value':value, 'from':account.address, 'gas': custom_gas})

        gas = int(gas*1.2)

        nonce = web3.eth.get_transaction_count(account.address)

        tx_dict = {
                    'from':account.address,
                    'value':value,
                    'nonce':nonce,
                    'gas':gas,
                }

        tx_dict = eip1559.get_gas_prices(CHAIN_ID_TO_NAME[web3.eth.chain_id], tx_dict)

        built_tx = tx.build_transaction(
                tx_dict
            )

        signed_tx = account.sign_transaction(built_tx)
        hash_tx = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logger.info(f'{account.address}: Transaction was sent')
        tx_passed = check_transaction(web3, hash_tx)

        if return_hash == False:
            return tx_passed
        else: 
            return hash_tx.hex()
        
    except Exception as e: 

        logger.error(f'{account.address}: {str(e)}')
        return 0

def get_deposit_wallet(private_key, deposit_addresses=DEFAULT_DEPOSIT_ADDRESSES):

    with open(deposit_addresses, 'r') as f: 
        OKX_addresses = f.read().splitlines()

    with open(DEFAULT_PRIVATE_KEYS, 'r') as f: 
       privates = f.read().splitlines()
            
    if len(OKX_addresses) != len(privates): 
        logger.error('privates don\'t match deposit addresses')
        sys.exit()

    n = privates.index(str(private_key))
    okx_address = OKX_addresses[n]

    return Web3.to_checksum_address(okx_address)


@error_handler('search erc20 balance')
#@logger.catch
def search_for_erc20_crosschain (private_key, coin_name,chain_names_list, min_balance):

    for chain_name in chain_names_list:

        web3 = Web3(Web3.HTTPProvider(RPC[chain_name]))
        account = web3.eth.account.from_key(private_key)
        current_chain = CHAINS_DATA[chain_name] # массив со значениями для текущей сети
            
        try: 
            coin_address = current_chain[coin_name]

        except: 
            continue
        
        get_balance = get_erc20_balance(web3, account, coin_address,fixed_decimal=True, return_decimal=True)

        balance = get_balance[0]
        decimals = get_balance[1]

        minimal_balance = intToDecimal(min_balance, decimals)

        if balance >= minimal_balance:

            return {
                'chain_name': chain_name, 
                'chain_id': web3.eth.chain_id,
                'token_address': coin_address,
                'balance': balance
                } 
    logger.warning(f'{account.address}: failed to find {coin_name}')
    return None 



def approve(web3, account, token_address, target, amount, approve_max= False): #amount в decimal

    address = account.address
    contract = web3.eth.contract(address = token_address, abi = ERC20_ABI)

    allowance = contract.functions.allowance(address, target).call()

    if allowance < amount: 
        logger.info(f'{account.address}: Approving tokens')
        
        if approve_max == True: 
            amount = (2 ** 256 - 1)
        
        approve_tx = contract.functions.approve(target,amount)
        tx = build_and_send_tx(web3, account, approve_tx)

        time.sleep(random.randrange(3,10))
        return tx
    
    else: 
        logger.info(f'{account.address}: Approve not needed')
        return 1
        
@error_handler('check tx')
def check_transaction(web3, hash_tx):

    tx_data = web3.eth.wait_for_transaction_receipt(hash_tx, timeout=MAX_TX_WAIT)

    if (tx_data['status'])== 1:
        logger.success(f'Transaction  {Web3.to_hex(tx_data["transactionHash"])}')
        return 1

    elif (tx_data['status'])== 0: 
        logger.success(f'Transaction  {Web3.to_hex(tx_data["transactionHash"])}')
        return 0
    
def get_proxy(private,mode ='http' ): 

    check_proxy()

    if '0x' in private:
        private = private[2:]

    with open(DEFAULT_PROXIES, 'r') as f: 
        proxies = f.read().splitlines()
        if len(proxies) == 0:
            return None
        
    with open(DEFAULT_PRIVATE_KEYS, 'r') as f: 
        privates = f.read().splitlines()
            
    n = privates.index(str(private))
    proxy = proxies[n]
    if mode == 'http':
        proxy = {
            'http': f'http://{proxy}',
            'https':f'http://{proxy}'
        }
    else: 
        loginpass, ipport=proxy.split('@')
        login, password = loginpass.split(':')
        ip, port = ipport.split(':')
        proxy = {
            'address': ip,
            'port': port,
            'password': password,
            'login': login
        }
    return proxy

def check_proxy():

    with open(DEFAULT_PROXIES, 'r') as f: 
        proxies = f.read().splitlines()
    with open(DEFAULT_PRIVATE_KEYS, 'r') as f: 
        privates = f.read().splitlines()

    if len(proxies) < len(privates) and len(proxies) != 0:
        logger.error('Proxy list doesnt match')
        sys.exit()

def intToDecimal(qty, decimal):
    return int(qty * int("".join(["1"] + ["0"]*decimal)))

def decimalToInt(price, decimal):
    return price/ int("".join((["1"]+ ["0"]*decimal)))

def pad32Bytes(data):
      s = data[2:]
      while len(s) < 64 :
        s = "0" + s
      return s


async def async_sleep(sleeping): 
    sleep_time = random.randrange(sleeping[0], sleeping[1])
    logger.info(f'Waiting {sleep_time} secs')
    await asyncio.sleep(sleep_time)

def sleep(sleeping):

    sleep_time = random.randrange(sleeping[0], sleeping[1])
    logger.info(f'Waiting {sleep_time} secs')
    time.sleep(sleep_time)

def get_random_proxy():
    with open(DEFAULT_PROXIES, 'r') as f: 
        proxies = f.read().splitlines()
        if len(proxies) == 0:
            return None
    
    proxy = random.choice(proxies)
    proxy = f'http://{proxy}'
    
    return proxy
    
def get_erc20_balance(web3, account_address, token_address, fixed_decimal = False, return_decimal = False): 

    contract = web3.eth.contract(address = token_address, abi = ERC20_ABI)
    decimals = contract.functions.decimals().call()
    balance = contract.functions.balanceOf(account_address).call()

    if fixed_decimal == False: 

        balance = decimalToInt(balance,decimals)

    if return_decimal == True:
        return [balance, decimals]
    else: 
        return balance

def get_contract(web3, address, abi): 
    
    contract = web3.eth.contract(address = address, abi = abi)

    return contract

def get_provider(name):

    web3 = Web3(Web3.HTTPProvider(RPC[name]))

    return web3



def generate_amount_in_range(range, rounding):

    n = random.randrange(rounding[0], rounding[1])
    amount = random.uniform(range[0], range[1])
    amount = round(amount, n)

    return amount

def round_down(n, decimals=0):
    multiplier = 10**decimals
    return math.floor(n * multiplier) / multiplier

def round_up(n, decimals=0):
    multiplier = 10**decimals
    return math.ceil(n * multiplier) / multiplier

def get_percent_from_value(value,percent, rounding):

    percent = random.uniform(percent[0], percent[1]+1)/100
    rounding = random.randrange(rounding[0], rounding[1]+1)

    value = percent * value

    return round_down(value, rounding)

@error_handler('send request')
def send_request(GET:bool, url, json=None, headers=None, proxy=None):
     
    if GET == True:
        response = requests.get(url,headers=headers,json=json, proxies=proxy)
    else: 
        response = requests.post(url,headers=headers,json=json, proxies=proxy)

    if str(response.status_code)[0] == '2' or str(response.status_code)[0] == '3':
        return response
    
    else: 
        time.sleep(3)
        raise Exception(f'API error: {response.status_code}: {response.text}')