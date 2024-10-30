from web3 import Web3
from web3.middleware import geth_poa_middleware
import time
import random
from config import ETH_GAS_MULT

data = {
    "Ethereum": {
        "rpc": ["https://rpc.ankr.com/eth", "https://ethereum.blockpi.network/v1/rpc/public",
                "https://eth-rpc.gateway.pokt.network"],
    },
    "POLYGON": {
        "rpc": ["https://polygon-bor.publicnode.com", "https://rpc.ankr.com/polygon"],
    },
    "BSC": {
        "rpc": ["https://bsc-dataseed.binance.org", "https://bsc-dataseed1.binance.org",
                "https://bsc-dataseed2.binance.org", "https://bsc-dataseed3.binance.org"],
    },
    "FANTOM": {
        "rpc": ["https://rpc.fantom.network", "https://rpc.ftm.tools", "https://rpc.ankr.com/fantom",
                "https://rpc2.fantom.network"],
    },
    "AVAX": {
        "rpc": ["https://avalanche-c-chain-rpc.publicnode.com", "https://avalanche-evm.publicnode.com", "https://1rpc.io/avax/c"],
    },
    "ARBITRUM": {
        "rpc": ["https://arb1.arbitrum.io/rpc", "https://arbitrum-one.public.blastapi.io", "https://1rpc.io/arb"],
    },
    "OPTIMISM": {
        "rpc": ["https://rpc.ankr.com/optimism", "https://optimism.publicnode.com"],
    },
    "CORE": {
        "rpc": ['https://rpc.coredao.org']
    },
    'BASE': {
        'rpc': ['https://base-rpc.publicnode.com']
    },
    'TAIKO': {
        'rpc': ['https://taiko.blockpi.network/v1/rpc/public', 'https://rpc.taiko.xyz']
    }
}


def get_gas_prices(chain, tx_dict=None, retries=3):
    if tx_dict is None:
        tx_dict = {}
    # Получаем список доступных RPC
    available_rpc = data[chain]["rpc"]
    for rpc in available_rpc:
        for _ in range(retries):
            try:
                web3 = Web3(Web3.HTTPProvider(rpc))

                # Если сеть - Polygon или Avalanche, инжектируем geth_poa_middleware
                if chain in ["POLYGON", "AVAX"]:
                    web3.middleware_onion.inject(geth_poa_middleware, layer=0)

                # Если сеть - BSC или Fantom, устанавливаем gasPrice и возвращаем tx_dict
                if chain in ["BSC", "FANTOM", 'CORE']:
                    tx_dict['gasPrice'] = Web3.to_wei(round(random.uniform(1.3 , 2.1),1), 'gwei')
                    return tx_dict

                # Рассчитываем maxFeePerGas
                gas_price = web3.eth.generate_gas_price()
                if gas_price is None:
                    gas_price = web3.eth.gas_price
                max_fee_per_gas = gas_price

                # Рассчитываем maxPriorityFeePerGas
                num_blocks = 5
                latest = web3.eth.get_block_number()
                start_block = max(0, latest - num_blocks)

                total_priority_fees = 0
                total_txs = 0

                # Итерируем по блокам для вычисления средней стоимости газа
                for block_number in range(start_block, latest + 1):
                    for _ in range(retries):
                        try:
                            block = web3.eth.get_block(block_number, full_transactions=True)
                            break
                        except Exception as e:
                            if 'block not found' in str(e).lower():
                                time.sleep(10)
                    else:
                        continue

                    for tx in block['transactions']:
                        total_priority_fees += tx['gasPrice']
                        total_txs += 1

                if total_txs == 0:
                    raise Exception("\n   Could not find transactions in last blocks")

                average_priority_fee = total_priority_fees // total_txs
                max_priority_fee_per_gas = min(average_priority_fee, max_fee_per_gas)

                # Добавляем в словарь полученные значения и возвращаем его
                
                if chain == 'POLYGON' or chain == 'AVAX':
                    tx_dict['maxFeePerGas'] = int(3.5*max_fee_per_gas)
                    tx_dict['maxPriorityFeePerGas'] = int(3.5 *max_priority_fee_per_gas)

                if chain =='AVAX':
                    tx_dict['maxFeePerGas'] = int(1.4*max_fee_per_gas)
                    tx_dict['maxPriorityFeePerGas'] = int(1.4 *max_priority_fee_per_gas)

                else:
                    tx_dict['maxFeePerGas'] = int(ETH_GAS_MULT*max_fee_per_gas)
                    tx_dict['maxPriorityFeePerGas'] = max_priority_fee_per_gas

                return tx_dict

            except ConnectionError as e:
                # В случае ошибки выводим сообщение
                print(f"  Connection error {rpc}: {str(e)}")
                continue