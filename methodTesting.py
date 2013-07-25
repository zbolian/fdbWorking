# Method testing

import csv
import glob
from datetime import datetime
from collections import defaultdict

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
    maxAFID = -1
    loop_ct = 0
    for row in csvReader:
        # Enforce headers are like we expect
        if loop_ct == 0:
            assert row[0]=='NSID'
            assert row[1]=='Child name'
            assert row[2]=='Parent name'
            assert row[3]=='AFID'
            loop_ct += 1
            continue
        # Add entry to dictionary and capture max AFID
        else:
            mappingDict[int(row[0])] = {'NSID':int(row[0]),'ChildName':row[1],'ParentName':row[2],'AFID':row[3]}
            t = row[3].split('-')
            tempID = int(t[1])
            if tempID > maxAFID:
                maxAFID=tempID

    return [mappingDict,maxAFID]

testDict = getIDMappingFile()
pause = 1

