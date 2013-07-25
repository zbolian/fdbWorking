import NetSuiteMod
from collections import defaultdict

# Determine legacy file settings
pr_flag = 'y' # Always do PR legacy files for now
#pr_flag = raw_input("Would you like to include PowerReviews legacy data this time? y/n: ")
#assert pr_flag.lower()=='y' or pr_flag.lower()=='n'

# Determine client count settings
cc_flag = raw_input("Would you like to count clients this time? y/n: ")
assert cc_flag.lower()=='y' or cc_flag.lower()=='n'
if cc_flag.lower() == 'y':
    overrideFilePath = raw_input('Please enter the full path of the most recent current client override file.') # Force user to enter the path of the most up to date override file.
    if overrideFilePath[-5:] != ".xlsx":
        try:
            false
        except:
            print "The overrides file must be a *.XLSX format."
            raise
    
# Set up default dictionaries
firstBookingsByClientTopName = defaultdict(lambda:None)
firstBookingsByClientTopNameAndProductID = defaultdict(lambda:None)

# Set up cursor to traverse NS tables
cursor = NetSuiteMod.getNetsuiteCursor()

# Pull id mapping translation table
idMappingList = NetSuiteMod.getIDMappingFile()
idMappingDict = idMappingList[0]
maxAFIDBV = idMappingList[1]
maxAFIDPR = idMappingList[2]

# Pull entity override file - temporary while they build out seperate revenue accounts in NetSuite
entityOverrides = NetSuiteMod.getEntityOverrideFile()

# Pull NS data into dictionaries
verticalsByID = NetSuiteMod.getNetsuiteVerticalIndex(cursor)
exchangeRatesByID = NetSuiteMod.getExchangeRateIndex(cursor)
NScustomersByID = NetSuiteMod.getNetsuiteCustomerIndex(cursor, verticalsByID)
itemsByID = NetSuiteMod.getNetsuiteItemsIndex(cursor)
contractsByID = NetSuiteMod.getNetsuiteContractsIndex(cursor, NScustomersByID, itemsByID)
monthlyDealCount = NetSuiteMod.getMontlyDealCount(contractsByID)
currenciesByID = NetSuiteMod.getCurrencyIndex(cursor)
paymentEntries = NetSuiteMod.getNetsuitePaymentEntries(cursor,exchangeRatesByID)
NSrevenueEntries = NetSuiteMod.readRevenueInput("c:/temp/fact_revenue_input.csv")
billFreqByID = NetSuiteMod.getNetsuiteBillingFreqEntries(cursor)
billingEntries = NetSuiteMod.getNetsuiteBillingsEntries(cursor,exchangeRatesByID)
impEntries, impEntriesNoDate = NetSuiteMod.getNetsuiteImplementationRecords(cursor)

#revenueEntries = getNetsuiteRevenueEntries(cursor) - Method not working because inability to tie revenue through automated pull

# Prep legacy PowerReviews files
if pr_flag.lower()=='y':
    bibleObj = NetSuiteMod.readLegacyBible("C:/Projects/fdb/BV west legacy files/Bible.csv")
    legacyRev = NetSuiteMod.getLegacyBibleRevenue(bibleObj)
    legacyBill = NetSuiteMod.getLegacyBibleBilling(bibleObj)
    legacyClient = NetSuiteMod.getLegacyBibleClients(bibleObj)
    expressObj = NetSuiteMod.readExpressFile(r'C:\Projects\fdb\BV west legacy files\Express.csv')
    expressClient = NetSuiteMod.getExpressClients(expressObj)
else:
    legacyRev,legacyBill,legacyClient,expressClient = [],[],[],[]
    
# Consolidate NetSuite and legacy
customersByID = NetSuiteMod.combineCustomerIndicies(NScustomersByID, legacyClient, expressClient, idMappingDict, maxAFIDBV, maxAFIDPR)
revenueEntries = NetSuiteMod.combineRevenue(NSrevenueEntries, legacyRev)

# Compute the first booking and go live dates
NetSuiteMod.computeFirstBookings(contractsByID, firstBookingsByClientTopName, firstBookingsByClientTopNameAndProductID)
goLiveDateByClientTopName = NetSuiteMod.computeClientGoLiveDates(revenueEntries, customersByID)

# Fix up the first booking and contract types 
NetSuiteMod.fixupCustomerFirstBookingsAndCohorts(customersByID, firstBookingsByClientTopName, goLiveDateByClientTopName)
NetSuiteMod.fixupContractTypes(contractsByID, firstBookingsByClientTopName)
#fixupLinkedTransactionLineItems(transactionLinesByKey, transactionLinksByKey)

# Prepare bookings data
monthlyCumulativeBookings = NetSuiteMod.getMonthlyCumulativeASFEntries(contractsByID)
monthlyIncrementalBookings = NetSuiteMod.getMonthlyIncrementalASFEntries(contractsByID)

# Identify BrandAnswers/Connections only clients
connectionsOnlyIDs = NetSuiteMod.getConnectionsOnlyIDs(monthlyCumulativeBookings[1])
customersByID = NetSuiteMod.fixUpConnectionsCustomer(customersByID,connectionsOnlyIDs,entityOverrides)
revenueEntries = NetSuiteMod.fixUpConnectionsRevenue(revenueEntries,connectionsOnlyIDs,entityOverrides)

# Prepare current client flags
if cc_flag.lower() =='y':
    clientOverrideList = NetSuiteMod.grabOverrides(overrideFilePath)
    clientList = NetSuiteMod.identifyCurrentClientsThroughTime(revenueEntries, customersByID, clientOverrideList, expressObj)
    NetSuiteMod.outputCurrentClientFactTable(clientList, r'c:/temp/fact_current_client.csv')

# Output updated bundling file
NetSuiteMod.outputClientMappingFile(customersByID)

# Output fact & dim tables
NetSuiteMod.outputCumulativeBookings(monthlyCumulativeBookings[0], "c:/temp/fact_bookings.csv")
NetSuiteMod.outputIncrementalBookings(monthlyIncrementalBookings, "c:/temp/fact_incremental_bookings.csv")
NetSuiteMod.outputRevenue(revenueEntries, "c:/temp/fact_revenue.csv")
NetSuiteMod.outputCustomers(customersByID, "c:/temp/dim_client.csv")
NetSuiteMod.outputProducts(itemsByID, "c:/temp/dim_product.csv")
NetSuiteMod.outputPayment(paymentEntries, "c:/temp/fact_payment.csv")
NetSuiteMod.outputBilling(billingEntries,"c:/temp/fact_billing.csv")
NetSuiteMod.outputDealCount(monthlyDealCount,"c:/temp/fact_dealcount.csv")
NetSuiteMod.outputImp(impEntries,"c:/temp/impEntries.csv")
NetSuiteMod.outputImpMiDate(impEntriesNoDate,"c:/temp/noDateEntries.csv")
NetSuiteMod.outputBillFreq(billFreqByID, "c:/temp/dim_billfreq.csv")
