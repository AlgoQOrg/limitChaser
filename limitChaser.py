import sys
from asyncio import run, gather
import ccxt
import ccxt.pro
from Base import Base

apiKey = 'xxx'
secret = 'xxx'
subaccount = 'xxx'

class LimitChaser(Base):
    def __init__(self, connection, pairs):
        super().__init__(connection)
        self.pairs = pairs
        for pair in self.pairs.keys():
            self.pairs[pair]['orderBook'] = None
            self.pairs[pair]['simMarketFilled'] = 0
            self.pairs[pair]['closed'] = False
            self.pairs[pair]['order'] = None
            self.pairs[pair]['orders'] = {}
            self.pairs[pair]['simOrders'] = {}
            self.pairs[pair]['lastTradeTimestamp'] = None

        self.postOnlyParams = {'postOnly': True}

    async def init(self): 
        # Seperate async init func, bcs in `__init__` it isn't possible to run asynchronous code
        self.markets = await self.connection.loadMarkets()
        for pair in self.pairs.keys():
            self.pairs[pair]['pip'] = self.markets[pair]['precision']['price']

    def selectPriceBasedOnMode(self, pair, orderBook, side, mode):
        if side == 'buy':
            if mode == 'best':
                price = orderBook['bids'][0][0]
            elif mode == 'quick':
                price = orderBook['asks'][0][0] - self.pairs[pair]['pip']
            else:
                raise Exception('This mode is not supported, only the modes best & quick are supported')
        elif side == 'sell':
            if mode == 'quick':
                price = orderBook['asks'][0][0]
            elif mode == 'best':
                price = orderBook['bids'][0][0] + self.pairs[pair]['pip']
            else:
                raise Exception('This mode is not supported, only the modes best & quick are supported')
        else:
            raise Exception('The side must be sell or buy')

        return self.connection.priceToPrecision(pair, price)
    
    def logOrder(self, order):
        pair = order['symbol']
        self.pairs[pair]['order'] = order
        self.pairs[pair]['lastTradeTimestamp'] = order['lastTradeTimestamp']
        print(f'{pair} - {order["side"].capitalize()} limit order placed at {order["price"]} for {order["amount"]} {self.markets[pair]["base"]}')
    
    def calcRemainingAmount(self, pair):
        totalLimitFilled = 0
        orders = self.pairs[pair]['orders']
        for orderId, order in orders.items():
            totalLimitFilled += order['filled']
        
        return totalLimitFilled - self.pairs[pair]['simMarketFilled']
    
    def allOrdersClosed(self):
        ordersClosed = True
        for pairData in self.pairs.values():
            if pairData['closed'] == False:
                ordersClosed = False
                break
        
        if ordersClosed:
            self.connection.close()
            print('All orders has been filled!')
            sys.exit()

    async def placeSimMarketOrder(self, pair):
        # TODO: Future - Add `simMarketPerc`
        side = self.pairs[pair]['simMarketSide']
        symbol = self.pairs[pair]['simMarket']
        remainingAmount = self.calcRemainingAmount(pair)
        simOrder = await self.marketOrder(symbol, side, remainingAmount)
        print(f'{symbol} - Simultaneous {side} market order is been filled for {simOrder["amount"]} {self.markets[pair]["base"]}')
        
        self.pairs[pair]['orders'][simOrder['id']] = simOrder  # type: ignore
        self.pairs[pair]['simMarketFilled'] += remainingAmount

    async def handleOrderBookChannel(self, pair, orderBook):
        mode = self.pairs[pair]['mode']
        if self.pairs[pair]['order'] == None:
            side = self.pairs[pair]['side']
            amount = self.connection.amountToPrecision(pair, self.pairs[pair]['amount'])
            price = self.selectPriceBasedOnMode(pair, orderBook, side, mode)
            order = await self.limitOrder(pair, side, amount, price, params=self.postOnlyParams)
            self.logOrder(order)
            
        if self.pairs[pair]['closed'] == False:
            if self.pairs[pair]['order']['side'] == 'buy' and \
                orderBook['bids'][0][0] >= self.pairs[pair]['order']['price'] + (self.pairs[pair]['threshold'] * self.pairs[pair]['pip']):
                self.connection.cancelAllOrders(pair)
                remainingAmount = self.calcRemainingAmount(pair)
                price = self.selectPriceBasedOnMode(pair, orderBook, 'buy', mode)
                order = await self.limitOrder(pair, 'buy', remainingAmount, price, params=self.postOnlyParams)
                self.logOrder(order)

            elif self.pairs[pair]['order']['side'] == 'sell' and \
                orderBook['asks'][0][0] <= self.pairs[pair]['order']['price'] - (self.pairs[pair]['threshold'] * self.pairs[pair]['pip']):
                self.connection.cancelAllOrders(pair)
                remainingAmount = self.calcRemainingAmount(pair)
                price = self.selectPriceBasedOnMode(pair, orderBook, 'sell', mode)
                order = await self.limitOrder(pair, 'sell', remainingAmount, price, params=self.postOnlyParams)
                self.logOrder(order)

    async def handleOrdersChannel(self, pair, order):
        self.pairs[pair]['order'] = order
        self.pairs[pair]['orders'][order['id']] = order
        
        if order['filled'] > 0 and order['status'] == 'closed':
            if self.pairs[pair]['simMarket'] != None and self.pairs[pair]['simMarketSide'] != None:
                await self.placeSimMarketOrder(pair)
            
            self.pairs[pair]['closed'] = True
            print(f'{pair} - {order["side"].capitalize()} limit order has been closed at {order["average"]} for {order["filled"]} {self.markets[pair]["base"]}')
            self.allOrdersClosed()

async def main():
    connection = ccxt.pro.ftx({
        'apiKey': apiKey,
        'secret': secret,
        'headers': {'FTX-SUBACCOUNT': subaccount} # remove this line if you don't use a subaccount
    })
    pairs = {
        'ETH/USD': {'side': 'sell', 'amount': 0.006, 'threshold': 1, 'mode': 'best', 'simMarket': None, 'simMarketSide': None},
    }
    '''
    pairs doc:
    side          - buy/sell
    amount        - ordered amount
    threshold     - if order is x pips below (ask) / above (bid) the threshold, replace order
    mode          - if side `buy` -> The `best` mode is the best bid price, the `quick` mode places a limit order 1 pip below the best ask price & visa verca for side `sell`
    simMarket     - simultaneous market buy/sell this symbol whenever your limit order gets (partly) filled
    simMarketSide - the side of the simultaneous market buy/sell
    '''

    limitChaser = LimitChaser(connection, pairs)

    await limitChaser.init()

    orderBookChannels = [limitChaser.watchOrderBook(pair) for pair in pairs.keys()]
    orderChannels = [limitChaser.watchOrders(pair) for pair in pairs.keys()]
    loops = orderBookChannels + orderChannels
    await gather(*loops)

run(main())