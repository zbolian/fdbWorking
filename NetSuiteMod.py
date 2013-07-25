# This is the Net Suite module.  It provides functions that interact with Net Suite that can be imported by other scripts

''''''''''''''' Contents '''''''''''''''
# The module is organized into 7 method classes - Set up, Data pull, Output, Fix up, Computation

#1) Set up - Import modules, grab cursor, set default dictionary
    # getNetsuiteCursor - Gets the cursor to traverse the Net Suite tables using configurations in fdb.ini file in setting directory

#2) Data Pull - Pull indices & data from Net Suite tables and return in dictionaries
    # readRevenueInput - Temporary method to pull *.csv file of revenue pulled from NS.  Ideally want to pull directly from tables in the future.
    # getCurrencyIndex - Pulls currency symbols by currency code
    # getExchangeRateIndex - Pulls exchange rate by currency and date
    # getNetsuiteVerticalIndex - Pulls vertical name by NS identifier
    # getNetsuiteItemsIndex - Pulls product name by NS identifier
    # getNetsuiteCustomerIndex - Pulls customer level information by NS identifier
    # getNetsuiteContractsIndex - Pulls contract information by NS identifier
    # getNetsuitePaymentEntries - Grabs NS payment entries by NS client identifier and month
    # getNetsuiteRevenueEntries - THIS METHOD DOES NOT CURRENTLY WORK.  Ideally should pull revenue from underlying tables.  Will replace readRevenueInput method when this works.
    # getNetsuiteBillingsEntries - Pulls net billing by NS ids

#3) Prepare legacy data from PowerReviews
    # prepLegacyBible - Prepares the client by client revenue & billing file such that it can be consolidated with the NetSuite extract

#4) Combine NetSuite and Legacy information
    # combineCustomerIndicies - combines the customer tables, and produces data to populate the dim_client table

#5) Fix up - Update data dictionaries based on desired criteria
    # fixupContractTypes - This updated the contracts dictionary to indicate whether the contract reflects and Uptick or Downtick
    # fixupCustomerFirstBookingsAndCohorts - Sets client go live date, cohort, and old never live flag

#6) Computation - Computes desired values based on raw data from Net Suite
    # getMonthlyCumulativeASFEntries - Gathers cumulative ASF entries by client and month
    # getMonthlyIncrementalASFEntries - Gathers incremental ASF entries by client and month
    # computeClientGoLiveDates - Computes the go live date for a give client base on go live criteria
    # computeFirstBookings - Computes the first booking date by top client & product

#7) Output - Output *.CSV files in desired format
    # outputCumulativeBookings
    # outputIncrementalBookings
    # outputCustomers
    # outputProducts
    # outputRevenue
    # outputPayment
    # outputBilling
    
''''''''''''''''''''''''''''''

''''''''''''''' Set up '''''''''''''''
import ConfigParser
from collections import defaultdict
from win32com.client import DispatchEx
from datetime import datetime
import os
import operator
import csv
import glob
import pyodbc
import time
from fdbMappings import *
from fdbUtils import *
from excel_constants import *

today = datetime(datetime.now().year,datetime.now().month,datetime.now().day)

# Set default dictionaries
missingCustomer = {
    "nsID": -1,
    "name": "None",
    "country": "Other",
    "region": "Other",
    "vertical": "Other",
    "parentID": -1,
    "topName": "None",
    "topID": -1,
    "firstBooking": None,
    "cohort": None,
    "entity":"BV"
}

missingProduct = {
    "nsID": -1,
    "name": "None",
    "familyName": "None"
}

# Tuple to identify clients that only have BrandAnswers/Connections Booking
connectionsOnlyProducts = (
    81,
    82,
    83,
    84,
    85,
    123,
    355,
    356,
    357
)

# Get the Net Suite cursor - This is used to traverse the tables in Net Suite.  It is a parameter for pretty much all of the functions in this module.
def getNetsuiteCursor():
    parser = ConfigParser.RawConfigParser()
    parser.read("../settings/fdb.ini")
    cnxn = pyodbc.connect(parser.get('Netsuite', 'connection_string'))
    return cnxn.cursor()

# This method pulls in the account family id mapping file and puts it into a dictionary.  It also captures the max account family id so that new entries can be added sequentially.
def getIDMappingFile():
    mappingFileList = glob.glob(r'C:\Projects\fdb\accountFamilyMapping\*.csv')

    # Grab the most recent mapping file based on the date prefix
    min_date = datetime(1990,1,1)
    mostRecentFile = 'No file found'
    for file in mappingFileList:
        temp = file[file.rfind('\\')+1:file.rfind('_')]
        date = datetime(int(temp[0:temp.find(".")]),int(temp[temp.find(".")+1:temp.rfind(".")]),int(temp[temp.rfind(".")+1:]))
        if date > min_date:
            min_date = date
            mostRecentFile = file

    #Import file
    csvReader = csv.reader(open(mostRecentFile,'rb'), delimiter=',', quotechar='"')
    mappingDict = defaultdict(dict)
    maxAFIDBV, maxAFIDPR = -1,-1
    loop_ct = 0
    for row in csvReader:
        # Enforce headers are like we expect
        if loop_ct == 0:
            assert row[0]=='NSID'
            assert row[1]=='Child name'
            assert row[2]=='Parent name'
            assert row[3]=='AFID'
            assert row[4]=='CIQ ID'
            assert row[5]=='BU'
            assert row[6]=='is_fortune500'
            assert row[7]=='is_ir500'
            assert row[8]=='CIQ Ult Parent'
            assert row[9]=='Customer origination'
            loop_ct += 1
            continue
        # Add entry to dictionary and capture max AFID
        else:
            mappingDict[str(row[0])] = {'NSID':str(row[0]),'ChildName':row[1],'ParentName':row[2],'AFID':row[3],'ciqID':str(row[4]),'BU':row[5],'isFortune500':int(row[6]),'isIr500':int(row[7]), 'ciqUltParent':row[8], 'custOrigination':row[9]}
            t = row[3].split('-')
            if t[1][0]=='1': # This is PR case
                tempID = int(t[1])
                if tempID > maxAFIDPR:
                    maxAFIDPR=tempID
            elif t[1][0]=='0': # This is BV case
                tempID = int(t[1])
                if tempID > maxAFIDBV:
                    maxAFIDBV=tempID
            else:
                print "Danger Will Robinson!  There is a crisis here!"
                raise

    return [mappingDict,maxAFIDBV,maxAFIDPR]

# This method pulls entity override file. This is to facilitate the breakout of Connections-only and Enterprise clients while they are still building out the seperate revenue account structure in NetSuite
def getEntityOverrideFile():
    mappingFileList = glob.glob(r'C:\Projects\fdb\entityOverridesFolder\*.csv')

    # Grab the most recent mapping file based on the date prefix
    min_date = datetime(1990,1,1)
    mostRecentFile = 'No file found'
    for file in mappingFileList:
        temp = file[file.rfind('\\')+1:file.rfind('_')]
        date = datetime(int(temp[0:temp.find(".")]),int(temp[temp.find(".")+1:temp.rfind(".")]),int(temp[temp.rfind(".")+1:]))
        if date > min_date:
            min_date = date
            mostRecentFile = file

    #Import file
    csvReader = csv.reader(open(mostRecentFile,'rb'), delimiter=',', quotechar='"')
    entityOverrideDict = defaultdict(dict)
    loop_ct = 0
    for row in csvReader:
        # Enforce headers are like we expect
        if loop_ct == 0:
            assert row[0]=='clientID'
            assert row[1]=='clientName'
            assert row[2]=='entity'
            assert row[3]=='note'
            loop_ct += 1
            continue
        # Add entry to dictionary and capture max AFID
        else:
            entityOverrideDict[str(row[0])] = {'clientID':str(row[0]),'clientName':row[1],'entity':row[2],'note':row[3]}

    return entityOverrideDict

''' This function pulls the manual overrides data from the specified file location '''
def grabOverrides(filename):

    # Set up excel application
    xlapp = DispatchEx("Excel.Application")
    xlapp.DisplayAlerts = False
    wb = xlapp.Workbooks.Open(filename)

    ''' Grab the overrides for specific client/date combinations '''
    ws = wb.Worksheets("override_by_client_date")
    ws.Activate

    # Select data in excel file
    assert ws.Cells(1,1).Value == "AFID"       # Ensure data is in expected structure
    assert ws.Cells(1,2).Value == "Parent Name"
    lastFilledCol = ws.Range("A1").End(xlToRight).Column
    lastFilledRow = ws.Range("A1").End(xlDown).Row
    data = ws.Range(ws.Cells(1,1),ws.Cells(lastFilledRow,lastFilledCol)).Value

    # Create dictionary from data 
    uniqueClientSet = set([])   # Set is used to ensure clients in spreadsheet are unique.  Throw error if not.
    overrideDict = {} # This dictionary will have the form {client:{date:override_value}}

    for row in range(1,lastFilledRow):  # Loop through rows (clients with overrides)

        #client = data[row][0].lower().encode('ascii', 'ignore') # Standardize client to be ascii and lower case
        client = data[row][0]
        
        # Enforce client uniqueness
        if client in uniqueClientSet:
            print "The client " + data[row][0] + " appears more than once in the Overrides sheet.  Please consolidate entries to be unique by company. The file path is " + filename + "."
            raise
        else:
            uniqueClientSet.add(client)

        dateDict = {} # Set up row dict in form {date:override_value}.  We'll have one of these for each unique client.
        uniqueDateSet = set([]) # Set is used to ensure dates in spreadsheet are unique.  Throw error if not.
        for col in range(2,lastFilledCol): # Loop through columns - dates of overrides (Start in column 3 now since we are leaving out cohort)
            
            # Enforce date uniqueness
            if data[0][col] in uniqueDateSet:
                print "The date " + str(data[0][col].month) + '/' + str(data[0][col].day) + '/' + str(data[0][col].year) + " appears more than once in the Overrides sheet.  Please consolidate entries to make dates unique."
                raise
            else:
                uniqueDateSet.add(data[0][col])
                
            # Fill date dict for this client
            month = date(data[0][col].year, data[0][col].month, data[0][col].day)
            if data[row][col]!=None:
                dateDict[month] = data[row][col]
            else:
                dateDict[month] = -1
                
        # Fill the client level dictionary
        overrideDict[client] = dateDict
        ''' End - "Grab the overrides for specific client/date combinations" '''   

    ''' Grab the overrides by client '''
    ws =wb.Worksheets("override_by_client")
    ws.Activate

    # Select data in excel file
    assert ws.Cells(1,1).Value == "NSID"       # Ensure data is in expected structure
    assert ws.Cells(1,2).Value == "Client name"
    lastFilledRow = ws.Range("A1").End(xlDown).Row
    data = ws.Range(ws.Cells(1,1),ws.Cells(lastFilledRow,1)).Value

    # Create a list of the entities to exclude
    entitiesToExclude = []      
    for row in range(1,lastFilledRow):
        if entitiesToExclude.count(data[row][0])>0:
            print "The entity " + str(data[row][0]) + " appears in the entities to exclude sheet more than once.  Please make this list unique."
            raise
        else:
            entitiesToExclude.append(str(int(data[row][0])))
    ''' End - "Grab the overrides by client '''

    # Close the excel application
    wb.Close()
    xlapp.DisplayAlerts = True
    xlapp.Quit()

    return [overrideDict, entitiesToExclude]

''''''''''''''' Data pull methods '''''''''''''''
# Read csv file of revenue (not reading directly from Netsuite yet, due to no documented way of pulling revenue directly).
# File is lines of Date (yyyymmdd), ProductID, ClientID, Recurring (0 or 1), Revenue
def readRevenueInput(filename):
    csvReader = csv.reader(open(filename, "rb"), delimiter=",", quoting=csv.QUOTE_NONE)
    entries = []
    for row in [row for row in csvReader][1:]: # Throw away first row (header row)
        time = datetime.strptime(row[0], "%Y%m%d")
        month = date(time.year, time.month, time.day)
        entry = {"month": month,
                 "itemID": int(row[1]),
                 "clientID": str(int(row[2])),
                 "recurring": int(row[3]),
                 "amount": float(row[4]),
                 "entity": "BV"
                 }
        entries.append(entry)
    return entries

def readLegacyBible(filename):
    # Prep orig data
    csvReader = csv.reader(open(filename, "rb"), delimiter=",", quoting=csv.QUOTE_NONE)
    entries = []
    ct = 0
    for row in [row for row in csvReader][0:]:
        ct+=1
        if ct == 1:
            headers = row
            continue
        for i in range(26,38): #month columns, col 26 is period of acquisition, col 9 is first month of data
            id = "PR"+row[1][-5:]
            amt = row[i]
            if amt == '':
                amt = '0'
            time = datetime(int(headers[i][0:4]),int(headers[i][4:6]),1)
            month = date(time.year, time.month, time.day)
            entry = {"id": id,
                     "month": month,
                     "name": row[0],
                     "b_r": row[2].lower(),
                     "payfreq": row[8],
                     "amount": float(amt)
                     }
            entries.append(entry)
    return entries


def readExpressFile(filename):
    # Prep orig data
    csvReader = csv.reader(open(filename, "rb"), delimiter=",", quoting=csv.QUOTE_NONE)
    entries = []
    ct = 0
    for row in [row for row in csvReader][0:]:
        ct+=1
        if ct == 1:
            headers = row
            continue
        for i in range(102,114): #month columns, col 102 is period of acquisition, col 85 is Jan 2011
            time = datetime(int(headers[i][0:4]),int(headers[i][4:6]),1)
            month = date(time.year, time.month, time.day)
            entry = {"clientId": row[0],
                     "month": month,
                     "recurring": 1,
                     "name": row[6],
                     "amount": int(row[i])
                     }
            entries.append(entry)
    return entries

def getLegacyBibleRevenue(legacy_bible):
    t_dict = defaultdict(lambda:0)
    for entry in legacy_bible: # collapse to ids
        if entry['b_r']!='r':
            continue
        key = (entry['id'],entry['month'])
        t_dict[key] += entry['amount']
    entries = []
    for key in t_dict: # prep list to mirror NetSuite return
        entry = {"month": key[1],
                 "itemID": -1,
                 "clientID": key[0],
                 "recurring": 1,
                 "amount": t_dict[key],
                 "entity":"PR"
                 }
        entries.append(entry)

    return entries

def getLegacyBibleBilling(legacy_bible):
    t_dict = defaultdict(lambda:0)
    for entry in legacy_bible: # collapse to ids
        if entry['b_r']!='b':
            continue
        key = (entry['id'],entry['month'])
        t_dict[key] += entry['amount']
    entries = []
    for key in t_dict: # prep list to mirror NetSuite return list
        entry = {"month": key[1],
                     "clientID": key[0],
                     "amount": t_dict[key]
                     }
        entries.append(entry)
        
    return entries

def getLegacyBibleClients(legacy_bible):
    customersByID = defaultdict(dict)
    for entry in legacy_bible:
        customersByID[entry['id']] = {'nsID':entry['id'], 'name': entry['name'],'parentID':entry['id'],'vertical':"Retail",'country':"US",'region':"North America", "entity":"PR"}
        
    return customersByID


def getExpressClients(data):
    customersByID = defaultdict(dict)
    for entry in data:
        customersByID[entry['clientId']] = {'nsID':entry['clientId'], 'name': entry['name'],'parentID':entry['clientId'],'vertical':"Retail",'country':"US",'region':"North America", "entity":"EX"}
        
    return customersByID

# Get translation of currency IDs from "Currencies" table.  Currency symbol (e.g. USD for US Dollars) by NS currency ID.
def getCurrencyIndex(cursor):
    """ Returns an index of currencies, keyed by internal id.
    Returns dict {id, {id, symbol}}"""
    print "Fetching Currencies from Netsuite...",
    currenciesByID = {}
    cursor.execute("SELECT currency_id, symbol FROM Currencies")
    rows = cursor.fetchall()
    for row in rows:
        currency = {"id": int(row[0]), "symbol": row[1] }
        currenciesByID[currency["id"]] = currency
    print "Done"
    return currenciesByID


# Get exchange rate dictionary by currency_id and date from the "CurrencyRates" table
def getExchangeRateIndex(cursor):
    """ Returns an index of exchange rates, keyed by foreign currency (relative to USD) and exchange daate
    Returns dict currencyID, {effectiveDate: rate}}"""
    print "Fetching Exchange Rates from Netsuite...",
    exchangeRate = defaultdict(float)
    cursor.execute("SELECT BASE_CURRENCY_ID, CURRENCY_ID, DATE_EFFECTIVE, EXCHANGE_RATE FROM CurrencyRates")
    rows = cursor.fetchall()
    for row in rows:
        if int(row[0]) == 1: #Only populate if we are looking at currency relative to USD
            key = (int(row[1]),row[2])
            exchangeRate[key] = float(row[3])
    print "Done"
    return exchangeRate


# Returns the vertical identifier and vertical name from the "Vertical" table.  Key return variable is vertical.
def getNetsuiteVerticalIndex(cursor):
    verticalsByID = {}
    cursor.execute("SELECT list_id, list_item_name FROM Vertical")
    rows = cursor.fetchall()
    for row in rows:
        vertical = {"nsID": int(row[0]), "name": row[1] }
        verticalsByID[vertical["nsID"]] = vertical
    return verticalsByID


# Retruns dictionary of product identifiers and product names from "Items" table.  Key return variable is product name.
def getNetsuiteItemsIndex(cursor):
    """ Returns an index of items, keyed by internal id.
    Returns dict {id, {id, name}}"""
    itemsByID = {-1: missingProduct}
    cursor.execute("SELECT item_id, name FROM Items")
    rows = cursor.fetchall()
    for row in rows:
        familyName = "Other"
        id = int(row[0])
        if id in productFamilyMap:
            familyName = productFamilyMap[id]

        item = {"nsID": id, "name": row[1], "familyName": familyName }
        itemsByID[item["nsID"]] = item
        
    return itemsByID


# This function returns information from the "Customers" table in Net Suite. Key return varaibls are customer name, contry, region, vertical
def getNetsuiteCustomerIndex(cursor, verticalsByID):
    """ Returns an index of companies, keyed by internal id.
    Returns dict {id, {id, name, country, vertical}}"""
    customersByID = {-1: missingCustomer}
    cursor.execute("SELECT customer_id, full_name, country, vertical_id, parent_id FROM Customers")
    rows = cursor.fetchall()
    for row in rows:
        verticalName = None
        verticalID = int(row[3] or 0)
        if verticalID in verticalsByID:
            verticalName = verticalsByID[verticalID]["name"]

        # Cleansing: Combine Media/Travel & Leisure/Retail
        if verticalName == "Media" or verticalName == "Travel & Leisure":
            verticalName = "Retail"

        countryCode = row[2]
        if countryCode in countryRegionMap:
            region = countryRegionMap[countryCode]
        else:
            region = "Other"

        customer = {"nsID": str(int(row[0])), "name": row[1], "country": countryCode, "region": region, "vertical": verticalName, "parentID": str(int(row[4] or 0)), "entity":"BV"}
        customersByID[customer["nsID"]] = customer
        
    return customersByID

def getConnectionsOnlyIDs(cumulativeBookings):
    connectionsOnlyIDs = []
    cumulativeBookingsSorted = sorted(cumulativeBookings.keys()) # Sort so we can easily get last date for which we have bookings
    lastmonth = cumulativeBookingsSorted[len(cumulativeBookingsSorted)-1]
 
    for clientID in cumulativeBookings[lastmonth]:
        connectionASF, otherASF = 0, 0
        if clientID == '5711' or clientID == '2576':
            pause = 1
        for prod in cumulativeBookings[lastmonth][clientID]:
            if prod in connectionsOnlyProducts:
                connectionASF += cumulativeBookings[lastmonth][clientID][prod]
            else:
                otherASF += cumulativeBookings[lastmonth][clientID][prod]
        if connectionASF > 0 and otherASF < 10: # allow 10 slop
            connectionsOnlyIDs.append(str(int(clientID)))

    return connectionsOnlyIDs

def combineCustomerIndicies(fromNetSuite, fromLegacy, fromExpress, idMappingDict, maxAFIDBV, maxAFIDPR):
    notInMappingFileCtBV, notInMappingFileCtPR = 1,1
    # Combine the customer indicies from NetSuite and the Legacy Bible
    customersByID = dict(fromNetSuite.items() + fromLegacy.items() + fromExpress.items())

    for customer in customersByID.values():
        parentID = customer["parentID"]
        if parentID and parentID!='0':
            customer["topID"] = customer["parentID"]
            customer["topName"] = makeUnicode(customersByID[customer["parentID"]]["name"])
        else:
            customer["topName"] = makeUnicode(customer["name"])
            customer["topID"] = customer["nsID"]

        # Handle case where client has been mapped already
        if customer["nsID"] in idMappingDict:
            customer["topName"] = makeUnicode(idMappingDict[customer["nsID"]]['ParentName'])
            customer["afID"] = idMappingDict[customer["nsID"]]['AFID']
            customer["BU"] = idMappingDict[customer["nsID"]]['BU']
            customer["ciqID"] = idMappingDict[customer["nsID"]]['ciqID']
            customer["isFortune500"] = idMappingDict[customer["nsID"]]['isFortune500']
            customer["isIr500"] = idMappingDict[customer["nsID"]]['isIr500']
            customer["ciqUltParent"] = idMappingDict[customer["nsID"]]['ciqUltParent']
            customer["custOrigination"] = idMappingDict[customer["nsID"]]['custOrigination']
        # Handle case where client has yet to be mapped.  Name should already be set to customer name, but need to create a new AFID.
        else:
            if customer["entity"] == 'BV':
                customer["afID"] =  "AF-"+str(maxAFIDBV + notInMappingFileCtBV).zfill(8)
                notInMappingFileCtBV+=1
            else:
                customer["afID"] =  "AF-"+str(maxAFIDPR + notInMappingFileCtPR).zfill(8)
                notInMappingFileCtPR+=1
            # Update non-AFID vars
            customer["BU"] = "TBD"
            customer["ciqID"] = "TBD"
            customer["isFortune500"] = -1
            customer["isIr500"] = -1
            customer["ciqUltParent"] = "TBD"
            customer["custOrigination"] = "Organic sale" #Assume new customer are organic for now (temporary as want this to be pushed into NetSuite soon)
            
        # Cleansing: P&G Intl maps to US
        if customer["topID"] in topIDRegionMap:
            customer["country"] = "Multi"
            customer["region"] = topIDRegionMap[customer["topID"]]
            
        # Cleansing: P&G Intl that isn't narrow enough (e.g. Brazil within Americas, needs to be South America)
        if customer["nsID"] in idRegionMap:
            customer["country"] = "Multi"
            customer["region"] = idRegionMap[customer["nsID"]]            

    return customersByID

def combineRevenue(fromNetSuite, fromLegacy):
    revenueEntries = fromNetSuite + fromLegacy
    return revenueEntries
'''
# Commented this out because I am planning to split gross billing and credit memos & need to figure out if that can be tracked in legacy
def combineBilling(fromNetSuite, fromLegacy):
    revenueBilling = fromNetSuite + fromLegacy
    return revenueBilling
'''

def fixUpConnectionsCustomer(customersByID,connectionsOnlyIDs,entityOverrides):
    for id in customersByID:
        if customersByID[id]["nsID"] in connectionsOnlyIDs: # Adjust for connections only
            customersByID[id]["entity"] = "CN"
        if customersByID[id]["nsID"] in entityOverrides: # Apply entity overrides for month
            customersByID[id]["entity"] = entityOverrides[customersByID[id]["nsID"]]['entity']
    return customersByID

def fixUpConnectionsRevenue(revenueEntries,connectionsOnlyIDs,entityOverrides):
    for entry in revenueEntries:
        if entry["clientID"] in connectionsOnlyIDs:
            entry["entity"] = "CN"
        if entry["clientID"] in entityOverrides: # Apply entity overrides for month
            entry["entity"] = entityOverrides[entry["clientID"]]['entity']
    return revenueEntries

# Returns the contract information from the "Contract" table.  Results in a contract by contract id.  Key variables customer id, product, isf, msf, asf, and contract effective date
def getNetsuiteContractsIndex(cursor, customersByID, itemsByID):
    contractsByID = {}
    cursor.execute("SELECT contract_id, customer_name_id, product_type_id, isf, msf_booking, effective_date, renewal_contract, live_adjustment, implementation_debooking FROM Contract")
    rows = cursor.fetchall()

    # Skip renewal contracts, contracts with no effective date, and contracts with zero MSF
    for row in [row for row in rows if row[6]!= 'T' and row[4] and row[5]]:

        if row[1]:
            customer = customersByID[str(int(row[1]))]
        else :
            customer = missingCustomer

        if row[2]:
            item = itemsByID[int(row[2])]
        else:
            item = missingProduct

        # In the past there was only one flag (adjustment_contract) that included all headwind.  At the beginning to calendar 2013, we renamed the adjustment_contract variable to live_adjustment and created another called implementation_debooking.
        # This will facilitate seperation between implementation debookings and live adjustments on a prospective basis, although all headwind in the past will now be seen as a live_adjustment irrespective of whether or not it was live.
        if row[7] or row[8]:
            if (row[7]=='F' and (row[8]=='F' or not(row[8]))) or (row[8]=='F' and (row[7]=='F' or not(row[7]))):
                booking_id = 1 # gross booking
            elif row[7]=='T' and (row[8]=='F' or not(row[8])):
                booking_id = 2 # Live Adjustment
            elif row[8]=='T' and (row[7]=='F' or not(row[7])):
                booking_id = 3 # Debooking
            else:
                print "There was an issue with the bookings type logic for contract record "+str(row[0])+". The live adjustment flag is "+row[7]+" and the debooking flag is "+row[8]+"."
                raise
        else:
            booking_id = -1 # Unknown

        contract = {"nsID": str(int(row[0])), "customer": customer, "item": item, "isf": row[3], "msf": row[4], "asf":(row[4] or 0) * 12, "effectiveDate": row[5], "booking_id": booking_id}
        contractsByID[contract["nsID"]] = contract

    return contractsByID
    
# Returns payment amounts by client and month from the "Transactions" and "Transaction_Lines" tables
def getNetsuitePaymentEntries(cursor, exchangeRatesByID):
    # Filters currently set on Payments in NetSuite
        # 1) Account Type == AcctRec (Accounts receiveable)
        # 2) Transaction Type == Payment

    """ Returns an index of payment entries, keyed by transaction id.
    Returns dict {id, {id, external id, id of renewed transaction, id of followon transaction, status}} """
    print "Fetching Payment Entries from Netsuite...",
    paymentEntries = []
    cursor.execute("SELECT transaction_lines.amount, transaction_lines.company_id, transactions.trandate, transactions.currency_id, transaction_lines.subsidiary_id FROM transaction_lines, transactions, accounts WHERE transaction_lines.transaction_id = transactions.transaction_id AND transaction_lines.account_id = accounts.account_id AND transactions.transaction_type = 'Payment' AND accounts.type_name = 'Accounts Receivable'")
    rows = cursor.fetchall()

    # Collapse payments by client/date
    summedAmounts = defaultdict(lambda: 0)
    for row in rows:
        # Grab currency adjustment if we are dealing with a subsidiary
        if row[3]!=1 and row[4]!=1:
            currencyAdjustment = exchangeRatesByID[(row[3],row[2])]  # Adjust foreign currency to USD
        else:
            currencyAdjustment = 1  # Dealing with USD
        d = row[2]
        month = date(d.year, d.month, 1)
        key = (int(row[1] or 0), month)
        summedAmounts[key]+= -1*row[0]*currencyAdjustment

    # Create payment entries
    for key in summedAmounts.keys():
        paymentEntry = {"amount": summedAmounts[key], "clientID": key[0], "month": key[1]}
        paymentEntries.append(paymentEntry)

    print "Done"
    return paymentEntries

def getNetsuiteBillingFreqEntries(cursor):
    print "Fetching Billing Frequency list..."
    cursor.execute("SELECT list_id, list_item_name FROM billing_cycle")
    rows = cursor.fetchall()
    billFreqDict = {-1:{'nsID':-1,'name':"Unknown"}}
    for row in rows:
        billFreqDict[int(row[0])] = {'nsID':int(row[0]),'name':row[1]}
    print "Done"
    return billFreqDict

# Returns Net Billing amounts by client and month from the "Transactions" and "Transaction_Lines" tables
def getNetsuiteBillingsEntries(cursor, exchangeRatesByID):
    # Filters currently set on Payments in NetSuite
        # 1) Account Type == AcctRec (Accounts receiveable)
        # 2) Transaction Type == Invoice or Credit Memo

    """ Returns an index of billing entries, keyed by transaction id.
    Returns dict {id, {id, external id, id of renewed transaction, id of followon transaction, status}} """
    print "Fetching Billing Entries from Netsuite...",
    billingEntries = []
    cursor.execute("SELECT transaction_lines.amount, transaction_lines.company_id, accounting_periods.starting, transactions.currency_id, transaction_lines.subsidiary_id, transactions.transaction_type, transactions.billing_frequency_id FROM transaction_lines, transactions, accounts, accounting_periods WHERE transaction_lines.transaction_id = transactions.transaction_id AND transactions.accounting_period_id = accounting_periods.accounting_period_id AND transaction_lines.account_id = accounts.account_id AND accounts.type_name = 'Accounts Receivable' AND (transactions.transaction_type = 'Invoice' OR transactions.transaction_type = 'Credit Memo')")
    rows = cursor.fetchall()

    # Collapse payments by client/date
    summedAmounts = defaultdict(lambda: 0)
    for row in rows:

        # Create link for invoice type dim table
        if row[5]=="Invoice":
            transType = 1
        elif row[5]=="Credit Memo":
            transType = 0
        else:
            transType = -1

        # Create a link to the billing frequency dim table
        if row[6]:
            billFreq = row[6]
        else:
            billFreq = -1
            
        # Grab currency adjustment if we are dealing with a subsidiary
        if row[3]!=1 and row[4]!=1:
            currencyAdjustment = exchangeRatesByID[(row[3],row[2])]  # Adjust foreign currency to USD
        else:
            currencyAdjustment = 1  # Dealing with USD
        d = row[2]
        month = date(d.year, d.month, 1)
        key = (int(row[1] or 0), month, transType, billFreq)
        summedAmounts[key]+= row[0]*currencyAdjustment

    # Create payment entries
    for key in summedAmounts.keys():
        billingEntry = {"amount": summedAmounts[key], "clientID": key[0], "month": key[1], "invID": key[2], "billFreqID": key[3]}
        billingEntries.append(billingEntry)

    print "Done"
    return billingEntries

# Returns Implementation records amounts by client and month from the implementations table
def getNetsuiteImplementationRecords(cursor):

    """ Returns an index of payment entries, keyed by transaction id.
    Returns dict {id, {id, external id, id of renewed transaction, id of followon transaction, status}} """
    print "Fetching Implementation Entries from Netsuite...",

    # Pull in implementation phase data
    imp_phase_dict = defaultdict(str)
    imp_phase_dict[-1] = "N/A"  
    cursor.execute("SELECT implementation_phase.list_id, implementation_phase.list_item_name FROM implementation_phase")
    rows = cursor.fetchall()
    for row in rows:
        imp_phase_dict[int(row[0])] = row[1]
        
    cursor.execute("SELECT implementations.implementation_customer_nam_id, implementations.projected_bv_launch, implementations.actual_client_launch, implementations.imp_phase_id, implementations.implementation_msf FROM implementations")
    rows = cursor.fetchall()

    # Collapse ASF by client/date
    impEntries = []
    missingDateList = []
    summedAmounts = defaultdict(lambda: 0)
    for row in rows:
        if imp_phase_dict[row[3]] == "Completed" or imp_phase_dict[row[3]] == "Cancelled" or imp_phase_dict[row[3]] =="Not Implemented - Retired":
            continue
        if (row[2] or row[1]):
            if row[2]:
                d = row[2]
            else:
                d = row[1]
            month = date(d.year, d.month, 1)
            key = (int(row[0] or 0), month, imp_phase_dict[row[3]])
            summedAmounts[key]+= (row[4] or 0)*12
        else:
            missingDateList.append([row[0],(imp_phase_dict[row[3]] or "N/A"),(row[4] or 0)*12])
            
    # Create payment entries
    for key in summedAmounts.keys():
        impEntry = {"amount": summedAmounts[key], "clientID": key[0], "month": key[1], "imp_phase":key[2]}
        impEntries.append(impEntry)

    print "Done"
    return [impEntries,missingDateList]

# This method is not functioning.  It needs to be finished.
#def getNetsuiteRevenueEntries(cursor):
#    """ Returns an index of revenue entries, keyed by transaction id.
#    Returns dict {id, {id, external id, id of renewed transaction, id of followon transaction, status}} """
#    print "Fetching Revenue Entries from Netsuite...",
#    revenueEntries = []
#
#    searchAccounts = ','.join(map(str, accountIDRecurringMap.iterkeys()))
#    cursor.execute("SELECT transaction_lines.amount, transaction_lines.account_id, transaction_lines.company_id, transaction_lines.item_id, transactions.trandate FROM transaction_lines, transactions where non_posting_line = 'No' and transaction_lines.transaction_id = transactions.transaction_id and transaction_lines.account_id in (" + searchAccounts + ")")
#    rows = cursor.fetchall()
#    for row in rows:
#        recurring = accountIDRecurringMap[int(row[1])]
#        d = row[4]
#        month = date(d.year, d.month, 1)
#        revenueEntry = {"amount": row[0], "recurring": recurring, "clientID": int(row[2] or 0), "itemID": int(row[3] or 0), "month": month}
#        revenueEntries.append(revenueEntry)
#
#    print "Done"
#    return revenueEntries

''''''''''''''' Fix up methods '''''''''''''''
# This method sets the variable that indicates whether the contract is an uptick or a downtick
def fixupContractTypes(contractsByID, firstBookingsByClientTopName):
    contractsByDate = sorted(contractsByID.values(), key=operator.itemgetter('effectiveDate'))
    for contract in contractsByDate:
        if contract['effectiveDate'] == firstBookingsByClientTopName[contract['customer']['topName']]:
            contractType = "New"
        elif contract['asf'] < 0:
            contractType = "Downtick"
        else:
            contractType = "Uptick"

        contract['contractType'] = contractType

# This method sets the go live date for the customer (and by default, the cohort) as well as the oldNeverLive flag
def fixupCustomerFirstBookingsAndCohorts(customersByID, firstBookingsByClientTopName, goLiveDateByClientTopName):
    # Guarantee the firstBooking attribute is on every customer
    for customer in customersByID.itervalues():
        topName = customer['topName']
        firstBooking = firstBookingsByClientTopName[topName]
        customer['firstBooking'] = firstBooking

        if firstBooking:
            customer['cohort'] = bvFY(firstBooking)
        else:
            customer['cohort'] = None

        goLive = goLiveDateByClientTopName[topName]
        if goLive:
            customer['goLiveCohort'] = bvFY(goLive)
        else:
            customer['goLiveCohort'] = None

        if customer['nsID'] in cohortOverrideDict:
            customer['cohort'] = cohortOverrideDict[customer['nsID']]

        if customer['cohort'] and customer['cohort'] < 2011 and not customer['goLiveCohort']:
            customer['oldNeverLive'] = 1
        else :
            customer['oldNeverLive'] = 0



''''''''''''''' Computation methods '''''''''''''''
# Returns the cumulative ASF paid by a client for a given product at one month intervals.
def getMonthlyCumulativeASFEntries(contractsByID):
    today = date.today()

    contractsByDate = sorted(contractsByID.values(), key=operator.itemgetter('effectiveDate'))

    contractsByMonth = defaultdict(list)

    for contract in contractsByDate:
        contractDate = contract['effectiveDate']
        month = date(contractDate.year, contractDate.month, 1)
        contractsByMonth[month].append(contract)

    productClientAccumulators = defaultdict(float)
    monthlyClientBooking = {}

    asfEntries = []

    sortedMonths = sorted(contractsByMonth.keys())

    for month in [month for month in sortedMonths if month <= today]:
        tempClientDict = {}

        monthContracts = contractsByMonth.get(month)

        for contract in monthContracts:
            key = (contract['item']['nsID'], str(contract['customer']['nsID']))
            productClientAccumulators[key] += contract['asf']

        for ((itemID,clientID),asf) in productClientAccumulators.iteritems():
            entry = {"itemID": itemID, "clientID": clientID, "month": month, "asf": round(asf, 4)}
            asfEntries.append(entry)
            if tempClientDict.has_key(clientID):
                if tempClientDict[clientID].has_key(itemID):
                    tempClientDict[clientID][itemID] += asf
                else:
                    tempClientDict[clientID][itemID] = asf
            else:
                tempClientDict[clientID] = {itemID:asf}
            
        monthlyClientBooking[month] = tempClientDict
        
    return [asfEntries,monthlyClientBooking]

# Returns the incremental ASF paid by a client for a given product at one month intervals.
def getMonthlyIncrementalASFEntries(contractsByID):
    today = date.today()

    contractsByDate = sorted(contractsByID.values(), key=operator.itemgetter('effectiveDate'))

    contractsByMonth = defaultdict(list)

    for contract in contractsByDate:
        contractDate = contract['effectiveDate']
        month = date(contractDate.year, contractDate.month, 1)
        contractsByMonth[month].append(contract)

    asfEntries = []

    sortedMonths = sorted(contractsByMonth.keys())
    for month in [month for month in sortedMonths if month <= today]:

        productClientContractTypeAccumulators = defaultdict(float)

        monthContracts = contractsByMonth.get(month)

        for contract in monthContracts:
            key = (contract['item']['nsID'], str(contract['customer']['nsID']), contract['contractType'], contract['booking_id'])
            productClientContractTypeAccumulators[key] += contract['asf']

        for ((itemID, clientID, contractType, bookingType),asf) in productClientContractTypeAccumulators.iteritems():
            entry = {"itemID": itemID, "clientID": clientID, "contractType": contractType, "bookingType": bookingType, "month": month, "asf": round(asf, 4)}
            asfEntries.append(entry)

    return asfEntries

def getMontlyDealCount(contractsByID):
    dealCountEntries = defaultdict(lambda:0)
    for contract in contractsByID:
        if contractsByID[contract]['booking_id']==1:
            key = (contractsByID[contract]['customer']['nsID'],dateToDateKey(contractsByID[contract]['effectiveDate']))
            if dealCountEntries.has_key(key):
                if contractsByID[contract]['effectiveDate'] not in dealCountEntries[key]['dealDateSet']:
                    dealCountEntries[key] = {'nsID':key[0],'dateKey':key[1],'count':dealCountEntries[key]['count']+1,'dealDateSet':dealCountEntries[key]['dealDateSet']+[contractsByID[contract]['effectiveDate']]}
            else:
                dealCountEntries[key] = {'nsID':key[0],'dateKey':key[1],'count':1,'dealDateSet':[contractsByID[contract]['effectiveDate']]}
    return dealCountEntries
    

# Process incoming revenue - input is list of {Date, ProductID, ClientID, Revenue} from Netsuite report
# - Go-live = Three consecutive months of rev rec >= $500
def computeClientGoLiveDates(revenueEntries, customersByID):
    goLiveRevenueAmount = 500

    goLiveDateByClientTopName = defaultdict(lambda:None)

    # Build index of (Date,ClientID)->Revenue
    revenueByDateAndClientTopName = defaultdict(float)
    for entry in revenueEntries:
        amount = entry["amount"]
        clientID = entry["clientID"]

        if clientID != -1 and amount and clientID in customersByID:
            key = (entry["month"], customersByID[clientID]["topName"])
            revenueByDateAndClientTopName[key] += amount

    for ((month, topName),amount) in revenueByDateAndClientTopName.iteritems():
        # If we already have an earlier goLive date found, skip this entry
        if topName in goLiveDateByClientTopName and month > goLiveDateByClientTopName[topName]:
            continue

        if bvFY(month) < 2011:
        # Special logic for old never live clients - go live requires 3 consecutive months of >= $500 revenue
            if amount >= goLiveRevenueAmount:
                oneMonth = nextMonth(month)
                twoMonths = nextMonth(oneMonth)
                key1 = (oneMonth, topName)
                key2 = (twoMonths, topName)
                if key1 in revenueByDateAndClientTopName and key2 in revenueByDateAndClientTopName:
                    if revenueByDateAndClientTopName[key1] >= goLiveRevenueAmount and revenueByDateAndClientTopName[key2] >= goLiveRevenueAmount:
                        goLiveDateByClientTopName[topName] = month
        else:
        # for new clients - go live on any positive revenue
            if amount > 0:
                goLiveDateByClientTopName[topName] = month

    return goLiveDateByClientTopName


# This method updated the first client bookings dictionary  using the contract effective date
def computeFirstBookings(contractsByID, firstBookingsByClientTopName, firstBookingsByClientTopNameAndProductID):
    # Record earliest booking date on the customer.
    for contract in contractsByID.itervalues():
        topName = contract['customer']['topName']

        if (not topName in firstBookingsByClientTopName) or not firstBookingsByClientTopName[topName]:
            firstBookingsByClientTopName[topName] = contract['effectiveDate']
        else:
            firstBookingsByClientTopName[topName] = min(contract['effectiveDate'], firstBookingsByClientTopName[topName])

        key = (topName, contract['item']['nsID'])
        if (not key in firstBookingsByClientTopNameAndProductID) or not firstBookingsByClientTopNameAndProductID[key]:
            firstBookingsByClientTopNameAndProductID[key] = contract['effectiveDate']
        else:
            firstBookingsByClientTopNameAndProductID[key] = min(contract['effectiveDate'], firstBookingsByClientTopNameAndProductID[key])

''' This function identifies current clients through time based on revenue (boolean is provided for various set time periods) '''
def identifyCurrentClientsThroughTime(revenueEntries, customersByID, overrideList, expressData):

    # Convert express data into list
    expressList = []
    for row in expressData:
        entry = {"month": row["month"],
                 "itemID": -1,
                 "clientID": row["clientId"],
                 "recurring": 1,
                 "amount": row["amount"],
                 "entity":"EX"
                 }
        expressList.append(entry)

    # Combine revenue entries with express data (note, express data is just flag but that shouldn't be a problem)
    combinedRevEntries = revenueEntries + expressList

    # Pull out two parts of override list
    overrideDict = overrideList[0]
    entitiesToExclude = overrideList[1]
    ### ZB - This could be the structural problem getting in the way of making the entity assignment time dependent.
    clientIdDict = {} # Format {AFID : NSID} - This dict will hold an arbitrary ID for a given bundle name

    # Build index of (Date,ClientID)->Revenue
    revenueByDateAndAccountName = defaultdict(float)
    revenueByDateAndClientTopName = defaultdict(float)
    uniqueClientList = []   # List contains unique list of client for sorting and lookup values
    uniqueDateList = []     # List contains unique list of revenue recognition dates

    # Capture unique list of account ids - sub top level client
    uniqueIDSet = set([])
    for entry in combinedRevEntries:
        uniqueIDSet.add(entry["clientID"])

    # Loop through all of the IDs we have and all the entries to get recurring revenue by client
    # Note - this nested loop is horrendously inefficient, but I don't have the time to come up with something cooler now.  Fix this later to save run time.
    for id in uniqueIDSet:
        
        for entry in combinedRevEntries:

            # Set high level variables
            amount = entry["amount"]
            clientID = entry["clientID"]

            # Subset to only recurring revenue numbers
            if entry["recurring"]!=1:
                continue

            # Only keep records that relate to this accont id
            if entry["clientID"] != id:
                continue

            # Exclude wholly excluded entities from override file
            if entitiesToExclude.count(clientID):  # Skip if this is an entity to exclude
                continue
            
            if clientID != -1 and amount and clientID in customersByID:

                topClientName = customersByID[clientID]["topName"].encode('ascii','ignore').lower() # Standardize top client name to match client names from override dictionary
                afID = customersByID[clientID]["afID"]
                             
                if uniqueClientList.count(afID) == 0:      # Update unique client list & ID dictionary
                        uniqueClientList.append(afID)
                if uniqueDateList.count(entry["month"]) == 0:       # Update unique data list
                    uniqueDateList.append(entry["month"])                             
                if clientIdDict.has_key(afID):
                    if clientIdDict[afID]['month'] < entry['month']:# Update assignment of AFID to customer id.  Handle such that client assignment goes in order BV, PR, CN, EX.
                        clientIdDict[afID] = {'id':clientID,'month':entry['month'],'entity':entry['entity']}
                    elif clientIdDict[afID]['month'] == entry['month'] and ((clientIdDict[afID]['entity']!='BV' and entry['entity']=='BV') or ((clientIdDict[afID]['entity']=='EX' or clientIdDict[afID]['entity']=='CN') and entry['entity']=='PR') or (clientIdDict[afID]['entity']=='EX' and entry['entity']=='CN')):
                            clientIdDict[afID] = {'id':clientID,'month':entry['month'],'entity':entry['entity']}
                else:
                    clientIdDict[afID] = {'id':clientID,'month':entry['month'],'entity':entry['entity']}
      
                key = (entry["month"], id, afID)
                revenueByDateAndAccountName[key] += amount # Increment if there is a positive value for an account that belongs to this client
        

    # Now that we have recurring revenue at the account level, collapse to the top parent level within entities
    # Note - this nested loop is also disgustingly inefficient.  "Look away, I'm hideous!!!" - Kramer
    for client in uniqueClientList:
        for acct_key in revenueByDateAndAccountName.keys():
            if acct_key[2]==client:
              key = (acct_key[0],acct_key[2])
              if revenueByDateAndAccountName[acct_key]>0.1:
                  revenueByDateAndClientTopName[key] += 1

    # Construct output dictionary
    uniqueClientList.sort() # It's important that these lists be sorted correctly for the following code to work correctly
    uniqueDateList.sort()
    outDataDict = {} # {ClientName : {Date1:revenueBool1, Date2:revenueBool2, ...}}
    
    for i in range(0,len(uniqueClientList)):    # Loop through the "rows" of the eventual output data - customers
        clientRevDict = defaultdict(lambda: 0)  # {Date1:revenueBool1, Date2:revenueBool2, ...} - default at 0

        for j in range(0,len(uniqueDateList)):  # Loop through the "columns" of the eventual output data - revenue dates
            key = (uniqueDateList[j],uniqueClientList[i])

            # Update revenue flags for this client
            if revenueByDateAndClientTopName[key] > 0:
                clientRevDict[uniqueDateList[j]] = 1
            else:
                clientRevDict[uniqueDateList[j]] = 0

        # Correct for adjustments - form Date1 = 1, Date2 = 0, Date3 = 1. Often occurs at the end of a financial period when accounts are trued up.
        UpDownUpCorrection = {}
        for j in range(0,len(uniqueDateList)):  # Loop through the "columns" of the eventual output data - revenue dates
            UpDownUpCorrection[uniqueDateList[j]] = clientRevDict[uniqueDateList[j]] # Default the value to the simple revenue boolean
            # Update the values based on the up/down criteria where applicable
            if j >= 1 and j < len(uniqueDateList)-1:
                if clientRevDict[uniqueDateList[j]]==0 and clientRevDict[uniqueDateList[j-1]]==1 and clientRevDict[uniqueDateList[j+1]]==1:
                    UpDownUpCorrection[uniqueDateList[j]] = 1

        # Update the row dict                
        outDataDict[uniqueClientList[i]] = UpDownUpCorrection

        # Add overrides
        if overrideDict.has_key(uniqueClientList[i]): # Does the override file have this client?  If so, continue
            for date in outDataDict[uniqueClientList[i]].keys():
                if overrideDict[uniqueClientList[i]].has_key(date): # Does the override file have this date for this client?  If so, continue.
                    if overrideDict[uniqueClientList[i]][date] != -1: # Does the override file have an override value for this date/client?  If so, update the value. (-1 means the value was blank)
                        outDataDict[uniqueClientList[i]][date] = overrideDict[uniqueClientList[i]][date]
        
    # Adjust for clients in the override file that may not have ever had revenue - added for inclusion of some Shopzilla gains 12/2012
    # This is yet another annoying nested loop that will have a long run time...
    for afid in overrideDict:
        if afid not in outDataDict: # First, identify override clients that have never had revenue & apply override value
            temp_dict = {}
            for date in overrideDict[afid]:
                if overrideDict[afid][date] == 1: 
                    temp_dict[date] = 1
                else:
                    temp_dict[date] = 0
            outDataDict[afid] = temp_dict
            for cust_id in customersByID: # Second, find an arbitrary client ID for the identified account family ids.
                if afid in clientIdDict or customersByID[cust_id]["afID"] != afid:
                    continue
                clientIdDict[afid]={'id':cust_id,'entity':customersByID[cust_id]['entity']}
         
    return [outDataDict, clientIdDict]        



''''''''''''''' Output Methods '''''''''''''''
def outputCumulativeBookings(entries, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter='|', quotechar='"', quoting=csv.QUOTE_ALL)
    writer.writerow(["Date", "Product", "Client", "ASF"])

    for entry in entries:
        outrow = [entry["month"].strftime("%Y%m%d"),
                  entry["itemID"],
                  entry["clientID"],
                  entry["asf"]
                  ]

        writer.writerow(outrow)

    outfile.close()

def outputIncrementalBookings(entries, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter='|', quotechar='"', quoting=csv.QUOTE_ALL)
    writer.writerow(["Date", "Product", "Client", "ASF", "Contract Type", "Booking Type"])

    for entry in entries:
        outrow = [entry["month"].strftime("%Y%m%d"),
                  entry["itemID"],
                  entry["clientID"],
                  entry["asf"],
                  entry["contractType"],
                  entry["bookingType"]
                  ]

        writer.writerow(outrow)

    outfile.close()

def outputBookings(entries, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter='|', quotechar='"', quoting=csv.QUOTE_ALL)
    writer.writerow(["Date", "Product", "Client", "ASF", "Booking ID"])

    for entry in entries:
        outrow = [entry["month"].strftime("%Y%m%d"),
                  entry["itemID"],
                  entry["clientID"],
                  entry["asf"],
                  entry["bookingID"],
                  ]

        writer.writerow(outrow)

    outfile.close()

def outputCustomers(customersByID, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter='|', quotechar='"', quoting=csv.QUOTE_ALL)
    writer.writerow(["ID", "Name", "AFID","Parent ID", "Parent Name", "Country", "Region", "Vertical", "First Booking", "Cohort", "GoLive Cohort", "Old Never Live","Entity", "CIQ ID", "BU", "Fortune500", "IR500", "CIQ Ult Parent","Customer origination"])

    for (id, customer) in customersByID.iteritems():

        outrow = [customer["nsID"],
                  csvFormat(customer["name"]),
                  customer["afID"],
                  customer["topID"],
                  csvFormat(customer["topName"]),
                  csvFormat(customer["country"]),
                  csvFormat(customer["region"]),
                  csvFormat(customer["vertical"]),
                  customer["firstBooking"],
                  customer["cohort"],
                  customer["goLiveCohort"],
                  customer["oldNeverLive"],
                  customer["entity"],
                  customer["ciqID"],
                  customer["BU"],
                  customer["isFortune500"],
                  customer["isIr500"],
                  customer["ciqUltParent"],
                  customer["custOrigination"]
                  ]
        
        writer.writerow(outrow)

    outfile.close()

def outputProducts(itemsByID, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter='|', quotechar='"', quoting=csv.QUOTE_ALL)
    writer.writerow(["ID", "Name", "Product Family"])

    for (id, item) in itemsByID.iteritems():
        outrow = [item["nsID"],
                  csvFormat(item["name"]),
                  csvFormat(item["familyName"]),
                  ]

        writer.writerow(outrow)

    outfile.close()

def outputBillFreq(billFreqByID, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter='|', quotechar='"', quoting=csv.QUOTE_ALL)
    writer.writerow(["ID", "Name"])

    for (id, item) in billFreqByID.iteritems():
        outrow = [item["nsID"],
                  csvFormat(item["name"])
                  ]

        writer.writerow(outrow)

    outfile.close()

def outputRevenue(entries, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_NONE)
    writer.writerow(["Date", "Product", "Client", "Recurring", "Revenue"])

    for entry in entries:
        outrow = [entry["month"].strftime("%Y%m%d"),
                  entry["itemID"],
                  entry["clientID"],
                  1 if entry["recurring"] else 0,
                  entry["amount"]
                  ]

        writer.writerow(outrow)

    outfile.close()

def outputPayment(entries, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_NONE)
    writer.writerow(["ClientID", "Amount", "DateKey"])

    for entry in entries:
        outrow = [entry["clientID"],
                  entry["amount"],
                  entry["month"].strftime("%Y%m%d")                  
                  ]

        writer.writerow(outrow)

    outfile.close()

def outputBilling(entries, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_NONE)
    writer.writerow(["ClientID", "InvID", "BillFreqID", "Amount", "DateKey"])

    for entry in entries:
        outrow = [entry["clientID"],
                  entry["invID"],
                  entry["billFreqID"],
                  entry["amount"],
                  entry["month"].strftime("%Y%m%d")
                  ]

        writer.writerow(outrow)

    outfile.close()

def outputDealCount(entries, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_NONE)
    writer.writerow(["ClientID", "DateKey", "DealCount"])

    for entry in entries:
        outrow = [entries[entry]["nsID"],
                  entries[entry]["dateKey"],
                  entries[entry]["count"]
                  ]

        writer.writerow(outrow)

    outfile.close()

def outputImp(entries, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_NONE)
    writer.writerow(["ClientID", "Amount", "DateKey","Imp Phase"])

    for entry in entries:
        outrow = [entry["clientID"],
                  entry["amount"],
                  entry["month"].strftime("%Y%m%d"),
                  entry["imp_phase"]
                  ]

        writer.writerow(outrow)

    outfile.close()

def outputImpMiDate(entries, filename):
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_NONE)
    writer.writerow(["ClientID", "Phase", "ASF"])

    for entry in entries:
        writer.writerow(entry)

    outfile.close()

def outputClientMappingFile(entries):
    filename = r"c:\Projects\fdb\accountFamilyMapping"+"\\"+str(today.year)+"."+str(today.month).zfill(2)+"."+str(today.day).zfill(2)+"_AF mapping file.csv"
    outfile = open(filename, "wb")
    writer = csv.writer(outfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["NSID", "Child name", "Parent name", "AFID", "CIQ ID", "BU", "is_fortune500", "is_ir500","CIQ Ult Parent", "Customer origination"])

    for key in entries:
        entry = entries[key]

        outrow = [entry["nsID"],
                  csvFormat(entry["name"]),
                  csvFormat(entry["topName"]),
                  entry["afID"],
                  entry["ciqID"],
                  entry["BU"],
                  entry["isFortune500"],
                  entry["isIr500"],
                  entry["ciqUltParent"],
                  entry["custOrigination"]
              ]

        writer.writerow(outrow)

    outfile.close()

''' This function outputs the fact table identifying current clients '''
def outputCurrentClientFactTable(outList, outfile):

    # Pull out two parts of output list
    outDict = outList[0]
    idDict = outList[1]

    outfile = open(outfile, "wb")
    writer = csv.writer(outfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["client_id", "date_key", "current_client"])

    # Make sorted lists of clients
    sortedClientList = []
    for client in outDict.keys():
        sortedClientList.append(client)
    sortedClientList.sort()

    for client in sortedClientList:     # Loop through sorted client list

        # Make sorted date list for this client
        sortedDateList = []
        for date in outDict[client].keys():
            sortedDateList.append(date)
        sortedDateList.sort()

        for date in sortedDateList:     # Loop through sorted date list
            month_str = str(date.month)
            if len(month_str) == 1:
                month_str = '0'+month_str
            str_date = str(date.year)+month_str+'01'    # Standardize date key formatting

            outrow = [idDict[client]['id'],
                      str_date,
                      outDict[client][date]
                      ]
            
            writer.writerow(outrow) 

    outfile.close()

