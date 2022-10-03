from abc import abstractmethod
import traceback

class Base:
    def __init__(self, connection):
        self.connection = connection
    
    # WS
    # Public
    async def watchOrderBook(self, pair):
        while True:
            try:
                orderbook = await self.connection.watchOrderBook(pair)
                await self.handleOrderBookChannel(pair, orderbook)
            except Exception:
                err = traceback.format_exc()
                print(err)
        await self.connection.close()
    
    @abstractmethod
    async def handleOrderBookChannel(self, pair, orderbook):
        pass
    
    async def watchTrades(self, pair):        
        while True:
            try:
                trades = await self.connection.watchTrades(pair)
                for trade in trades:
                    await self.handleTradesChannel(pair, trade)
            except Exception:
                err = traceback.format_exc()
                print(err)
        await self.connection.close()
    
    @abstractmethod
    async def handleTradesChannel(self, pair, trade):
        pass
    
    
    # Private
    async def watchOrders(self, pair):        
        while True:
            try:
                orders = await self.connection.watchOrders(pair)
                for order in orders:
                    await self.handleOrdersChannel(pair, order)
            except Exception:
                err = traceback.format_exc()
                print(err)
        await self.connection.close()

    @abstractmethod
    async def handleOrdersChannel(self, pair, order):
        pass

    # CCXT
    # Public

    # Private
    async def marketOrder(self, pair, side, amount, params=None):
        if params != None:
            marketOrder = await self.connection.create_order(pair, 'market', side, amount, None, params)
        else:
            marketOrder = await self.connection.create_order(pair, 'market', side, amount, None)

        message = f'Market order has been placed (side: {side},  amount: {marketOrder["amount"]})'
        
        return marketOrder
    
    async def limitOrder(self, pair, side, amount, price, params=None):
        if params != None:
            limitOrder = await self.connection.create_order(pair, 'limit', side, amount, price, params)
        else:
            limitOrder = await self.connection.create_order(pair, 'limit', side, amount, price)
        
        message =  f'Limit order has been placed (side: {side}, price: {limitOrder["price"]}, amount: {limitOrder["amount"]})'

        return limitOrder