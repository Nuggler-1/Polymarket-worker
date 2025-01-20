
RPC = {
    'POLYGON': 'https://polygon-bor-rpc.publicnode.com',
    'BASE': 'https://base-rpc.publicnode.com'
}

WALLET_SLEEP = [100, 3800] #задержка между кошельками | так же включается себя задержку между парами
RANDOMIZE = False #перемешать порядок кошельков

TIMEOUT = 10_000 #таумаут на появление элемента на странице
PROXY_MODE = 'HTTP' #HTTP или SOCKS5

#=======FORKS RUNNER================

TOTAL_AMOUNT = [2,5] #объем вилки (суммарный для двух акков)
SLEEP_BETWEEN_WALLETS_IN_FORK = [5, 100] #ожидание между кошельками внутри одной вилки
SLEEP_BETWEEN_FORKS = [10, 900] #ожидание между вилками 
BETS_DEVIATION_PERCENT = 0 # на сколько процентов может отклоняться объем вилки, чтобы баланс не был 1 к 1 | чтобы отключить - 0

CLOSE_WALLET_SLEEP_IN_FORK = [10, 20] # закрытие вилок: задержка между кошельками внутри вилки
CLOSE_WALLET_SLEEP_BETWEEN_FORKS = [100, 200] # закрытие вилок: задержка между вилками

#=======BETS RUNNER================

#Поделит количество кошельков на столько частей сколько маркетов и откроет по ним сделки 
PERCENT_OF_BALANCE_TO_BET = [3,9] #процент от баланса сколько ставить

#Откуда взять маркет айди. Нужно зайти на страничку нужного маркета, прожать ctrl+shift+i, вкладка "сеть", перезагрузить страницу и кликнуть на нужный маркет в интерфейсе (например на камалу или на трампа)
# и в запросах появится его айди 
#https://clob.polymarket.com/rewards/markets/0xc6485bb7ea46d7bb89beb9c91e7572ecfc72a6273789496f78bc5e989e4d1638
#вот так выглядит запрос, соответственно нужно скопировать айди и вставить в MARKET_BETS

MARKET_BETS = [
    ['0xdd22472e552920b8438158ea7238bfadfa4f736aa4cee91a6b86c39ead110917', 'YES'],
    ['0x475e0fd32b211c0cfe6755638efceba2373d01a7224c7750f77f978db104f639', 'NO'],
    ['0xc6485bb7ea46d7bb89beb9c91e7572ecfc72a6273789496f78bc5e989e4d1638', 'NO'],
    ['0x3d31558105899ab4025075b92cfb127fae4be0e9644a6895466aa50e2de37e72', 'YES']

] #маркеты на которые хотим поставить ставки

#=======RELAY DEPOSIT================
CHAINS_BRIDGE_FROM = ['ARBITRUM', 'OPTIMISM', 'BASE']
MIN_BALANCE_TO_SEE = 10

#=======BINANCE DEPOSIT==============
AMOUNT_TO_DEPOSIT = [17,23]
API_KEY     = ""
API_SECRET  = ""

#=======WITHDRAW FROM POLYMARKET=====
AMOUNT_TO_WITHDRAW = [18, 23]
WITHDRAW_ALL = False

#=======UTILITY SETTINGS=============

ERR_ATTEMPTS = 3
MAX_BALANCE_WAIT = 500
MAX_GAS_PRICE = 500
MAX_TX_WAIT = 500
ETH_GAS_MULT = 1


#=======[REDACTED] RUNNER================
MARKET_ID = '' #condition id
TOKEN_ID = ''

AMOUNT_OF_TRADES = None
SLEEP_BETWEEN_TRADES =  None
MAX_WAIT_IF_SOMEONE_ELSE_IS_IN_MARKET = None
IGNORE_ASK_SIZE = None
