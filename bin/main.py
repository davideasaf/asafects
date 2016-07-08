import datetime
import json
import sys, os
import time
import util
import requests

###############################################
# Constants/Globals
###############################################

# BASE_URL = "http://www.thisisarealwebsite.corm"
BASE_PRACTICE_URL = "https://api-fxpractice.oanda.com/"
BASE_URL = "https://api-fxtrade.oanda.com/"
EX_RATE_URL = "http://api.fixer.io/latest"
DEBUG_LOGGER = util.getDebugLogger()
OUTPUT_LOGGER = util.getOutputLogger()

#WHITELISTS
PATTERN_WHITELIST = [
    'Double Top',
    'Head and Shoulders',
    'Inverse Head and Shoulders',
    'Rectangle',
    'Channel Up',
    'Channel Down'
]
LARGEST_SPREAD = 7
AMOUNT_PER_TRADE = 100

###############################################
# Classes
###############################################

class Trade:
    def __init__(self, instr, units, side, type, TP, SL, autochartId):
        self.instrument = instr
        self.units = units
        self.side = side
        self.type = type
        self.takeProfit = TP
        self.stopLoss = SL
        self.autochartId = autochartId

    def __str__(self):
        return "%s: %i units of %s. TP: %s SL: %s" % \
               (self.side, self.units, self.instrument, self.takeProfit, self.stopLoss)


    # def __repr__(self):
    #     return self.__str__(self)

    def toDict(self):
        #TODO: return a proper dictionary representation of this class to output to Osiris.
        #Create dictionary
        returnDict = {"x" : self.x}

        #Filter out blank entries
        returnDict = dict((k, v) for k, v in returnDict.iteritems() if v or v == 0)

        return returnDict

    def executeTrade(self, apiKey):
        """
        Description:
        Parameters:
        Returns:
        """
        try:
            executeTradeUrl = BASE_PRACTICE_URL + "v1/accounts/656251/orders"
            DEBUG_LOGGER.info("URL requesting: %s" % executeTradeUrl)
            headers = {'Authorization': "Bearer " + apiKey}
            payload = {'instrument': self.instrument,  'units': self.units, 'side': self.side, 'type': self.type,
                       'takeProfit': self.takeProfit, 'stopLoss': self.stopLoss}
            executeTradeResponse = requests.post(executeTradeUrl, headers=headers, data=payload)
            #TODO Handle responses that are not 200s
            if executeTradeResponse.status_code != 200:
                message = executeTradeResponse.content
                message = message.replace('\t','').replace('\n','').replace('\\','')
                sendTextNotification(message)
            pass

        except Exception, ex:
            errorMessage = "ERROR: Unable to execute trade: %s %s..." % (type(ex), ex)
            DEBUG_LOGGER.error(errorMessage)
            raise Exception(errorMessage)

###############################################
# Helper Methods
###############################################
def parseConfig():
    config = util.getConfig()
    practiceKey = ""
    liveKey = ""

    for configTuple in config.items("API"):
        if configTuple[0] == "practice_key":
            practiceKey = configTuple[1]
        elif configTuple[0] == "live_key":
            liveKey = configTuple[1]

    return practiceKey, liveKey

def getFavTrades(apiKey):
    """
    Description:
    Parameters:
    Returns:
    """
    try:
        favTradesUrl = BASE_URL + "labs/v1/signal/autochartist?type=chartpattern"
        DEBUG_LOGGER.info("URL requesting: %s" % favTradesUrl)
        headers = {'Authorization': "Bearer " + apiKey}
        favTradesResponse = requests.get(favTradesUrl, headers=headers)

        return favTradesResponse.json()

    except Exception, ex:
        errorMessage = "ERROR: Unable to get Auto Chart's Favorite Trades: %s %s..." % (type(ex), ex)
        DEBUG_LOGGER.error(errorMessage)
        raise Exception(errorMessage)

def buildTradeObject(tradeData, prices):
    """
    Description:
    Parameters:
    Returns:
    """

    #Prepare Parameters
    # pipMultiplier = the amount needed to multiply a rate to get the pip value (JPY pip vs Regular pip)
    if tradeData['pip'] == "0.0001":
        pipMultiplier = 10000
    else:
        pipMultiplier = 100

    #Reference of AutoChartID to put into cache:
    autochartId = tradeData['id']

    instrument = tradeData['instrument']
    type = "market"
    if (tradeData['meta']['direction'] is 1):
        side = "buy"
        takeProfit = tradeData['data']['prediction']['pricelow']

    else:
        side = "sell"
        takeProfit = tradeData['data']['prediction']['pricehigh']

    #Get stop loss
    for price in prices:
        if price['instrument'] == instrument:
            #The Same distance from CurPrice to TP will be the same distance from curPrice to StopLoss
            if side is "buy":
                curPrice = price['ask']
                #Only Make trades that are able to hit the TP
                if takeProfit < curPrice:
                    return
                stopLoss = curPrice - (takeProfit - curPrice)
                pipDistance = (takeProfit - curPrice) * pipMultiplier

            if side is "sell":
                curPrice = price['bid']
                #Only Make trades that are able to hit the TP
                if takeProfit > curPrice:
                    return
                stopLoss = curPrice + (curPrice - takeProfit)
                pipDistance = (curPrice - takeProfit) * pipMultiplier

            #Only Make trades that have a sufficient pip distance
            if pipDistance < 30:
                return

    #Get Units to trade
    priceForBase = 0
    if ("USD" in instrument):
        pipValue = AMOUNT_PER_TRADE / pipDistance
        unitsToBuy = pipValue * pipMultiplier * curPrice
    else:
        #Get price for the BASE/HOME pair (BASE/USD)
        basePair = instrument[:instrument.index("_")]
        priceForBase = getPriceInUSD(basePair)
        pipValue = (AMOUNT_PER_TRADE/priceForBase) / pipDistance
        unitsToBuy = pipValue * priceForBase * 10000

    if priceForBase != 0:
        DEBUG_LOGGER.debug("\n\nautochartId: %s | instrument: %s | side: %s\ntakeProfit: %s | curPrice: %s | stopLoss: "
                           "%s\npipDistance: %s | pipValue: %s | priceForBase: %s\nunitsToBuy: %s\n\n" % \
        (autochartId, instrument, side, takeProfit, curPrice, stopLoss, pipDistance, pipValue, priceForBase, unitsToBuy))
    else:
        DEBUG_LOGGER.debug("\n\nautochartId: %s | instrument: %s | side: %s\ntakeProfit: %s | curPrice: %s | stopLoss: "
                           "%s\npipDistance: %s | pipValue: %s | unitsToBuy: %s\n\n" % \
        (autochartId, instrument, side, takeProfit, curPrice, stopLoss, pipDistance, pipValue, unitsToBuy))

    #Create Trade Obj
    newTrade = Trade(instrument, int(unitsToBuy), side, type, takeProfit, stopLoss, autochartId)
    return newTrade

def getPriceInUSD(basePair):
    try:
        # rateUrl = EX_RATE_URL
        # DEBUG_LOGGER.info("URL requesting: %s" % rateUrl)
        # payload = {'base': basePair, 'symbols': 'USD'}
        #
        # rateUrlResponse = requests.get(rateUrl, params=payload)
        #
        # return rateUrlResponse.json()['rates']['USD']

        rateUrl = "http://finance.yahoo.com/d/quotes.csv?e=.csv&f=sl1d1t1&s=%sUSD=X" % basePair
        DEBUG_LOGGER.info("URL requesting: %s" % rateUrl)
        rateUrlResponse = requests.get(rateUrl)
        rate  = rateUrlResponse.text.split(',')[1]
        return float(rate)


    except Exception, ex:
        errorMessage = "ERROR: Unable to get Exchange Rate for Base Pair %s: %s %s..." % basePair, (type(ex), ex)
        DEBUG_LOGGER.error(errorMessage)
        raise Exception(errorMessage)

def getTradeObjects(tradeOpportunities, apiKey):
    tradesToMake = []

    #instrumentsAvail= List of instruments account is able to trade
    instrumentsAvail, instrumentToPip= getInstrumentsAvailToTrade(apiKey)

    #prices= List of prices for TradeOpportunities Instruments
    prices = getInstrumentPrices(tradeOpportunities, apiKey)
    instrumentsToRemove = getInstrumentRemovalList(prices)


    #CHECK IF TRADE OPPORTUNITY IS TRADABLE BY OANDA & worth it via the spread
    for tradeOpportunity in tradeOpportunities:
        if tradeOpportunity['instrument'] not in instrumentsAvail and tradeOpportunity['instrument'] in instrumentsToRemove:
            tradeOpportunities.remove(tradeOpportunity)
        else:
            # Get Pip location in instrument
            tradeOpportunity['pip'] = instrumentToPip[tradeOpportunity['instrument']]
            # Build Trade Object
            trade = buildTradeObject(tradeOpportunity, prices)
            # Add Trade object to list of trades to recursively execute. Avoid adding backed out trades
            if trade != None:
                tradesToMake.append(trade)
    #If tradeOpportunity passes tests, make trade object

    return tradesToMake

def getInstrumentRemovalList(prices):
    instrumentalRemovalList = []

    #For Spreads that are to large, add to removal list
    for price in prices:
        spread = (price['ask'] - price['bid']) * 10000
        if spread > LARGEST_SPREAD:
            instrumentalRemovalList.append(price['instrument'])

    return instrumentalRemovalList

def getInstrumentsAvailToTrade(apiKey):
    #Get Available instruments the account can trade
    instrumentList = []
    instrumentPipDict = {}
    try:
        instrumentsAvailUrl = BASE_URL + "v1/instruments?accountId=415660"
        DEBUG_LOGGER.info("URL requesting: %s" % instrumentsAvailUrl)
        headers = {'Authorization': "Bearer " + apiKey}
        instrumentsAvailResponse = requests.get(instrumentsAvailUrl, headers=headers)
        #Make JSON object response
        instrumentsAvailJson = instrumentsAvailResponse.json()
    except Exception, ex:
        errorMessage = "ERROR: Unable to get Instruments Available from Account: %s %s..." % (type(ex), ex)
        DEBUG_LOGGER.error(errorMessage)
        raise Exception(errorMessage)
    #Parse response into a list of isntruments
    for instrumentObj in instrumentsAvailJson['instruments']:
        instrument = instrumentObj['instrument']
        pip = instrumentObj['pip']
        instrumentList.append(instrument)
        instrumentPipDict[instrument] = pip

    return instrumentList, instrumentPipDict

def getInstrumentPrices(tradeOpportunities, apiKey):
    #Get Instruments from tradeOpportunities
    instrumentsList = []
    for tradeOpportunity in tradeOpportunities:
        instrumentsList.append(tradeOpportunity['instrument'])
    #Join instrument prices to put as a parameter for price request
    instrumentString = ','.join(instrumentsList)

    try:
        getPricesUrl = BASE_URL + "v1/prices"
        DEBUG_LOGGER.info("URL requesting: %s" % getPricesUrl)
        payload = {'instruments': instrumentString}
        headers = {'Authorization': "Bearer " + apiKey}
        priceResponse = requests.get(getPricesUrl, headers=headers, params=payload)
        #Make JSON object response
        pricesJson = priceResponse.json()
    except Exception, ex:
        errorMessage = "ERROR: Unable to get instrument prices from Oanda: %s %s..." % (type(ex), ex)
        DEBUG_LOGGER.error(errorMessage)
        raise Exception(errorMessage)

    return pricesJson['prices']

def sendTextNotification(message):
    try:
        textBeltUrl = "http://textbelt.com/text"
        payload = {'number': '9253259538', 'message': message}
        textBeltResponse = requests.post(textBeltUrl, data=payload)

    except Exception, ex:
        errorMessage = "ERROR: Unable to send text message: %s %s..." % (type(ex), ex)
        DEBUG_LOGGER.error(errorMessage)
        raise Exception(errorMessage)

###############################################
# Main
###############################################
def main():
    startTime = time.time()
    DEBUG_LOGGER.info("#------------------------------------------------")
    DEBUG_LOGGER.info("Starting collector execution.")

    #Get cache - by default it is just a dictionary
    cacheList = util.readCache()

    #Parse the config
    DEBUG_LOGGER.info("Parsing config.")
    practiceKey, liveKey = parseConfig()

    #List of Trade opportunities from AutoChartist dat
    tradeOpportunities = []
    #New Trades made counter
    newTradeCount = 0
    error = False
    try:
        #get AutoChart data
        autoChartData = getFavTrades(liveKey)

        for tradeOpportunity in autoChartData['signals']:
            # Check chance of possibility
            id = tradeOpportunity['id']
            prob = tradeOpportunity['meta']['probability']
            endPredictionPeriod = tradeOpportunity['data']['prediction']['timeto']
            chartPattern = tradeOpportunity['meta']['pattern']
            # if (prob > 73 and endPredictionPeriod > time.time() and chartPattern in PATTERN_WHITELIST and id not in cacheList):
            if (prob > 60):
                tradeOpportunities.append(tradeOpportunity)

        #Get list of trades to Execute if Trade opportunities exist
        if tradeOpportunities:
            tradesToExecute = getTradeObjects(tradeOpportunities, liveKey)
            for trade in tradesToExecute:
                OUTPUT_LOGGER.info("--Executing Trade: %s", trade)
                # trade.executeTrade(practiceKey)
                #Add +1 New Trade
                newTradeCount+=1
                #Add AutochartID to cache so that the same chart is not used to execute a trade
                cacheList.append(trade.autochartId)

        #Print to Output Logger:
        OUTPUT_LOGGER.info("Time: %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
        OUTPUT_LOGGER.info("New Trades Made: %d" % (newTradeCount))
        OUTPUT_LOGGER.info("#------------------------------------------------\n\n\n")



    except Exception as ex:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        errorMessage = "ERROR: Unknown exception occurred on line %s. Error: %s %s" % (exc_tb.tb_lineno, type(ex), str(ex))
        DEBUG_LOGGER.error("FAILED+++++COLLECTOR+++++FAILED")
        DEBUG_LOGGER.error(errorMessage)
        #Send Notifcation of Error
        sendTextNotification(errorMessage)
        error = True

    #Write the cache to disk if there was no error
    if not error:
        util.saveCache(cacheList)
        pass

    DEBUG_LOGGER.info("Finished execution in %.2f seconds." % (time.time() - startTime))
    DEBUG_LOGGER.info("#------------------------------------------------\n\n\n")

if __name__ == "__main__":
    main()