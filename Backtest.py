from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
import argparse
import datetime
from datetime import timedelta
import pandas as pd
import numpy as np
import backtrader as bt
import backtrader.feeds as btfeeds
import backtrader.indicators as btind
from backtrader.analyzers import (SQN, SharpeRatio)
from market_profile import MarketProfile
import time

data = pd.read_csv('/home/milo/Dropbox/Codigos/Data/ES_1min(2018)Ninja.csv', parse_dates=True, index_col='Date')
commission, margin, mult = 0.85, 20, 20.0

class DataPrep(object):
    def mp_poc(self):
        global pocs
        '''Calculates the POC for each Trading Session during the week'''
        na0 = np.where((data.index.dayofweek == 6) & (data.index.hour == 18) & (data.index.minute == 0)) #for IB (17, 0)
        nb0 = np.where((data.index.dayofweek == 4) & (data.index.hour == 16) & (data.index.minute == 0))#for IB (15, 59)
        na1 = np.where(((data.index.dayofweek == 0)|(data.index.dayofweek == 1)|(data.index.dayofweek == 2)\
            |(data.index.dayofweek == 3)) & (data.index.hour == 16) & (data.index.minute == 30))#for IB (15, 31)
        nb1 = np.where(((data.index.dayofweek == 0)|(data.index.dayofweek == 1)|(data.index.dayofweek == 2)\
            |(data.index.dayofweek == 3)) & (data.index.hour == 16) & (data.index.minute == 15))#for IB (15, 14)
        nmaster = np.concatenate([na0[0], nb0[0], na1[0], nb1[0]])
        nmaster = nmaster[nmaster>=na0[0][0]]
        nmaster.sort()
        mp = MarketProfile(data, tick_size=0.25)
        data['POC'] = np.nan
        for i,k in zip(nmaster[0::2], nmaster[1::2]):
            a = data.index[i]
            b = data.index[k]
            mp_slice = mp[a:b]
            data.loc[b, 'Points'] = mp_slice.poc_price
        pocs = data.Points.dropna().values
        data['POC'] = data.Points.fillna(method='ffill')
        data['PPOC'] = np.nan

    def lower_PPOC(self):
        '''If the Close price is below the POC, it calculates the last lower POC'''
        for x in range(len(pocs)-1,0,-1):
            n = data[(data.Points == pocs[x-1])]
            a = np.where(pocs[x::-1] < pocs[x])
            if len(a[0]) == 0:
                continue
            else:
                data.loc[(data.POC == pocs[x]) & (data.Close < data.POC) & (data.index >= n.index[0]), 'PPOC'] = pocs[x-a[0][0]]
            for y in pocs[x-a[0][0]-1::-1]:
                if y < pocs[x]:
                    if (data[(data.POC == pocs[x]) & (data.Close < data.POC) & (data.Close < data.PPOC) & (data.index >= n.index[0])].empty):
                        break
                    else:
                        data.loc[(data.POC == pocs[x]) & (data.Close < data.POC) & (data.Close < data.PPOC) & (data.index >= n.index[0]), 'PPOC'] = y
    def upper_PPOC(self):
        '''If the Close price is above the POC, it calculates the last upper POC'''
        for x in range(len(pocs)-1,0,-1):
            n = data[(data.Points == pocs[x-1])]
            a = np.where(pocs[x::-1] > pocs[x])
            if len(a[0]) == 0:
                continue
            else:
                data.loc[(data.POC == pocs[x]) & (data.Close > data.POC) & (data.index >= n.index[0]), 'PPOC'] = pocs[x-a[0][0]]
            for y in pocs[x-a[0][0]-1::-1]:
                if y > pocs[x]:
                    if (data[(data.POC == pocs[x]) & (data.Close > data.POC) & (data.Close > data.PPOC) & (data.index >= n.index[0])].empty):
                        break
                    else:
                        data.loc[(data.POC == pocs[x]) & (data.Close > data.POC) & (data.Close > data.PPOC) & (data.index >= n.index[0]), 'PPOC'] = y

class PandasData(btfeeds.PandasData):
    lines = ('POC', 'PPOC', )

    params = (
        ('open', 'Open'),
        ('high', 'High'),
        ('low', 'Low'),
        ('close', 'Close'),
        ('volume', 'Volume'),
        ('openinterest', None),
        ('POC', -1),
        ('PPOC', -1),
    )

class MultiDataStrategy(bt.Strategy):
    '''
    This strategy operates on 2 datas. The expectation is that the 2 datas are
    correlated and the 2nd data is used to generate signals on the 1st
      - Buy/Sell Operationss will be executed on the 1st data
      - The signals are generated using a Simple Moving Average on the 2nd data
        when the close price crosses upwwards/downwards
    The strategy is a long-only strategy
    '''
    params = dict(
        stake=1,
        printout=True,)

    def log(self, txt, dt=None):
        if self.p.printout:
            dt = dt or self.data.datetime[0]
            dt = bt.num2date(dt)
            print('%s, %s' % (dt.isoformat(), txt))

    def notify_order(self, order):
        print('{}: Order ref: {} / Type {} / Status {}'.format(
            self.data.datetime.datetime(0),
            order.ref, 'Buy' * order.isbuy() or 'Sell',
            order.getstatusname()))

        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return  # Await further notifications

        if order.status == order.Completed:
            if order.isbuy():
                self.log(
                    'BUY EXECUTED, Size: %.2f, Ref: %d, Price: %.5f, Cost: %.5f' %
                    (order.size,order.ref,order.executed.price,
                    order.executed.value))
                
                self.buyprice = order.executed.price
                
            else:  # Sell
                self.log('SELL EXECUTED, Size: %.2f, Ref: %d,Price: %.5f, Cost: %.5f' %
                        (order.size,order.ref,order.executed.price,
                        order.executed.value))
        
            self.bar_executed = len(self)

        elif order.status in [order.Expired, order.Canceled, order.Margin,  order.Rejected]:
            self.log('%s ,' % order.Status[order.status])
            pass  # Simply log

        if not order.alive() and order.ref in self.orefs:
            self.orefs.remove(order.ref)

        # Allow new orders
        self.orderid = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log('OPERATION PROFIT, GROSS %.5f, NET %.5f' %
                (trade.pnl, trade.pnlcomm))    

    def __init__(self):
        # To control operation entries
        self.orderid = None
        # Indicators
        poc = btind.SimpleMovingAverage(self.data0.POC, period=1, plotname='POC')
        ppoc = btind.SimpleMovingAverage(self.data0.PPOC, period=1, plotname='PPOC')
        self.atr = bt.talib.ATR(self.data0.high, self.data0.low, self.data0.close, period=14)
        self.ematr = btind.ExponentialMovingAverage(self.atr, period=89)
        self.dataclose = self.data0.close
        self.anchor = 3.0
        self.expand = 1.0
        self.signal1 = btind.CrossOver(self.dataclose, poc, plotname='POC')
        self.signal2 = btind.CrossOver(self.dataclose, ppoc, plotname='PPOC')
        #self.trailing = True
        self.flag=True

    def next(self):
        global o1, o2, o3, o4, o5, o6, o1pnl, o2pnl, o3pnl, o4pnl, o5pnl

        pos = self.getposition(self.data0)  # for the default data (aka self.data0 and aka self.datas[0])
        comminfo = self.broker.getcommissioninfo(self.data0)
        pnl = comminfo.profitandloss(pos.size, pos.price, self.data0.close[0])

        if self.orderid:
            return  # if an order is active, no new orders are allowed
        '''if self.p.printout:
            txt = ','.join(
            ['%04d' % len(self.data0),
            self.data0.datetime.datetime(0).isoformat(),
            'Profit : %d' % pnl])
        print(txt)'''

        if not self.position:  # not yet in market
            #self.trailing = True 
            if ((self.signal1 == 1.0) or (self.signal1 == -1.0) or (self.signal2 == 1.0) or (self.signal2 == -1.0)) and self.flag==True\
                and self.atr > self.ematr:

                o1 = self.buy(exectype = bt.Order.Stop, price=(self.data.close[-1] + self.anchor), size=self.p.stake)
             
                print(self.datetime.datetime(0),' : Oref %d / Buy Stop %d at %.5f' % (
                            o1.ref, o1.size, self.data.close[-1]))
                
                o2 = self.sell(exectype=bt.Order.Stop,price=(self.data.close[-1] - self.anchor), size=self.p.stake, oco=o1)
                
                print(self.datetime.datetime(0),' : Oref %d / Sell Stop %d at %.5f' % (
                            o2.ref, o2.size, o2.price))

                self.orefs = [o1.ref, o2.ref]
                self.flag=False
        else:
            
            if self.atr > 2.5:
                self.expand = 2.0
            else:
                self.expand = 1.0

            if (pos.size==self.p.stake) and (len(self.orefs)==0):

                o3 = self.sell(exectype=bt.Order.Stop, price=(float(o1.executed.price)-self.anchor*self.expand),
                            size=self.p.stake*3)
                
                print(self.datetime.datetime(0),' : Oref %d / Sell Stop %d at %.5f' % (
                            o3.ref, o3.size, o3.price))

                self.orefs.append(o3.ref)

            elif(pos.size==self.p.stake*-1) and (len(self.orefs)==0):

                o3 = self.buy(exectype=bt.Order.Stop, price=(float(o2.executed.price)+self.anchor*self.expand),
                            size=self.p.stake*3)
                
                print(self.datetime.datetime(0),' : Oref %d / Buy Stop %d at %.5f' % (
                            o3.ref, o3.size, o3.price))

                self.orefs.append(o3.ref)

            if (pnl > 5*8) and o3.alive():
                self.close()
                self.broker.cancel(o3)
                #self.trailing = True
                self.flag =True

            '''if (pnl > 50*2) and (pos.size == self.p.stake) and self.trailing:

                ot = self.sell(size=self.p.stake, exectype=bt.Order.StopTrail, trailamount=1.0, parent=o1)
                
                self.trailing = False

            if (pnl > 50*2) and (pos.size == self.p.stake) and self.trailing:

                ot = self.buy(size=self.p.stake, exectype=bt.Order.StopTrail, trailamount=1.0, parent=o2)

                self.trailing = False'''

            if (pos.size==self.p.stake*2):
                o2pnl = round((o3.executed.price-o2.executed.price)*(o2.executed.size+o3.executed.size)*(mult/2), 5)
                if (len(self.orefs)==0):
                    o4 = self.sell(exectype=bt.Order.Stop, price=(float(o2.executed.price)-self.anchor*self.expand),
                    size=self.p.stake*6)
                
                    print(self.datetime.datetime(0),' : Oref %d / Sell Stop %d at %.5f' % (
                        o4.ref, o4.size, o4.price))

                    self.orefs.append(o4.ref)
                
                if (pnl > (25 + abs(o2pnl))):
                    self.close()
                    self.broker.cancel(o4)
                    self.flag =True

            elif (pos.size==self.p.stake*2*-1):
                o2pnl = round((o3.executed.price-o1.executed.price)*(o1.executed.size+o3.executed.size)*(mult/2), 5)                         
                if (len(self.orefs)==0):
                    o4 = self.buy(exectype=bt.Order.Stop, price=(float(o1.executed.price)+self.anchor*self.expand),
                    size=self.p.stake*6)
                
                    print(self.datetime.datetime(0),' : Oref %d / Buy Stop %d at %.5f' % (
                        o4.ref, o4.size, o4.price))

                    self.orefs.append(o4.ref)

                if (pnl > (25 + abs(o2pnl))):
                    self.close()
                    self.broker.cancel(o4)
                    self.flag =True
            
            if (pos.size==self.p.stake*4):
                o3pnl = round((o4.executed.price-o3.executed.price)*(o3.executed.size+o4.executed.size)*(mult/1.5), 5)
                if (len(self.orefs)==0):
                    o5 = self.sell(exectype=bt.Order.Stop, price=(float(o2.executed.price)-self.anchor*self.expand),
                    size=self.p.stake*12)
                
                    print(self.datetime.datetime(0),' : Oref %d / Sell Stop %d at %.5f' % (
                        o5.ref, o5.size, o5.price))

                    self.orefs.append(o5.ref)

                if (pnl > (25 + abs(o2pnl + o3pnl))):
                    self.close()
                    self.broker.cancel(o5)
                    self.flag =True

            elif (pos.size==self.p.stake*4*-1):
                o3pnl = round((o4.executed.price-o3.executed.price)*(o3.executed.size+o4.executed.size)*(mult/1.5), 5)

                if (len(self.orefs)==0):
                    o5 = self.buy(exectype=bt.Order.Stop, price=(float(o1.executed.price)+self.anchor*self.expand),
                    size=self.p.stake*12)
                
                    print(self.datetime.datetime(0),' : Oref %d / Buy Stop %d at %.5f' % (
                        o5.ref, o5.size, o5.price))

                    self.orefs.append(o5.ref)

                if (pnl > (25 + abs(o2pnl + o3pnl))):
                    self.close()
                    self.broker.cancel(o5)
                    self.flag =True

            if (pos.size==self.p.stake*8):
                o4pnl = round((o5.executed.price-o4.executed.price)*(o4.executed.size+o5.executed.size)*(mult), 5)
                if (len(self.orefs)==0):
                    o6 = self.sell(exectype=bt.Order.Stop, price=(float(o2.executed.price)-self.anchor*self.expand),
                    size=self.p.stake*24)
                
                    print(self.datetime.datetime(0),' : Oref %d / Sell Stop %d at %.5f' % (
                        o6.ref, o6.size, o6.price))

                    self.orefs.append(o6.ref)

                if (pnl > (25 + abs(o2pnl + o3pnl + o4pnl))):
                    self.close()
                    self.broker.cancel(o6)
                    self.flag =True

            elif (pos.size==self.p.stake*8*-1):
                o4pnl = round((o5.executed.price-o4.executed.price)*(o4.executed.size+o5.executed.size)*(mult), 5)

                if (len(self.orefs)==0):
                    o6 = self.buy(exectype=bt.Order.Stop, price=(float(o1.executed.price)+self.anchor*self.expand),
                    size=self.p.stake*24)
                
                    print(self.datetime.datetime(0),' : Oref %d / Buy Stop %d at %.5f' % (
                        o6.ref, o6.size, o6.price))

                    self.orefs.append(o6.ref)

                if (pnl > (25 + abs(o2pnl + o3pnl + o4pnl))):
                    self.close()
                    self.broker.cancel(o6)
                    self.flag =True            

            if (pos.size==self.p.stake*16) or (pos.size==self.p.stake*16*-1):
                o5pnl = round((o6.executed.price-o5.executed.price)*(o5.executed.size+o6.executed.size)*(mult), 5)
                if (pnl > (25 + o2pnl + o3pnl + o4pnl + o5pnl)):
                    self.close()
                    self.flag=True           

    def stop(self):
        print('==================================================')
        print('Starting Value - %.2f' % self.broker.startingcash)
        print('Ending   Value - %.2f' % self.broker.getvalue())
        print('==================================================')

def runstrategy():

    DataPrep.mp_poc(data)
    DataPrep.lower_PPOC(data)
    DataPrep.upper_PPOC(data)
    data.drop(columns=['Points'])

    args = parse_args()

    # Create a cerebro
    cerebro = bt.Cerebro()

    # Add the 1st data to cerebro
    df=PandasData(dataname=data, name ="Minutes Data", timeframe=bt.TimeFrame.Seconds, compression=5)
    cerebro.adddata(df)

    # Create the 2nd data
    '''data1 = data.resample('H').last()
    data1['open'] = data.resample('H').first()
    data1['high'] = data.resample('H').max()
    data1['low'] = data.resample('H').min()
    data1 = data1.dropna()
    data1['median'] = (data1.high + data1.low) / 2.0
    data1['count'] = range(0, len(data1))
    x_ = data1['count'].rolling(lrperiod).mean()
    y_ = data1['close'].rolling(lrperiod).mean()
    mx = data1['count'].rolling(lrperiod).std()
    my = data1['close'].rolling(lrperiod).std()
    c = data1['count'].rolling(lrperiod).corr(data1.close)
    slope = c * (my/mx)
    inter = y_ - slope * x_
    data1['lin_reg'] = data1['count'] * slope + inter
    
    # Add the 2nd data to cerebro
    df1=PandasData(dataname=data1, name="Hourly Data", timeframe=bt.TimeFrame.Minutes, compression=60)
    cerebro.adddata(df1)'''

    # Add the strategy
    cerebro.addstrategy(MultiDataStrategy,
                        stake=args.stake)

    # Add the commission - only stocks like a for each operation
    cerebro.broker.setcash(args.cash)

    # Add the commission - only stocks like a for each operation
    cerebro.broker.setcommission(
        commission=commission, margin=margin, mult=mult)

    # Add the analyzers we are interested in
    cerebro.addanalyzer(SharpeRatio, timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(SQN, _name="sqn")

    cerebro.addwriter(bt.WriterFile, csv=args.writercsv, rounding=4)

    # And run it
    cerebro.run(runonce=not args.runnext,
                preload=not args.nopreload,
                oldsync=args.oldsync)

    # Plot if requested
    #if args.plot:
    cerebro.plot(numfigs=args.numfigs, volume=True, zdown=False)

def parse_args():
    parser = argparse.ArgumentParser(description='MultiData Strategy')

    parser.add_argument('--cash', default=100000, type=int,
                        help='Starting Cash')

    parser.add_argument('--runnext', action='store_true',
                        help='Use next by next instead of runonce')

    parser.add_argument('--nopreload', action='store_true',
                        help='Do not preload the data')

    parser.add_argument('--oldsync', action='store_true',
                        help='Use old data synchronization method')

    parser.add_argument('--commperc', default=0.000, type=float,
                        help='Percentage commission (0.005 is 0.5%%')

    parser.add_argument('--stake', default=1, type=int,
                        help='Stake to apply in each operation')

    parser.add_argument('--plot', '-p', action='store_true',
                        help='Plot the read data')

    parser.add_argument('--writercsv', '-wcsv', action='store_true',
                        help='Tell the writer to produce a csv stream')

    parser.add_argument('--numfigs', '-n', default=1,
                        help='Plot using numfigs figures')

    return parser.parse_args()


if __name__ == '__main__':
    runstrategy()
