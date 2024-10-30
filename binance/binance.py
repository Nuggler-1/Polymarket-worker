import time
import ccxt
from termcolor import cprint
import random

from loguru import logger

def binance_withdraw(address, amount_to_withdrawal, symbolWithdraw, network, API_KEY, API_SECRET):

    account_binance = ccxt.binance({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot'
        }
    })

    try:
        account_binance.withdraw(
            code    = symbolWithdraw,
            amount  = amount_to_withdrawal,
            address = address,
            tag     = None, 
            params  = {
                "network": network
            }
        )
        logger.success(f"{address} | {amount_to_withdrawal}")
    except Exception as error:
        logger.error(f"{address} | {error}")


