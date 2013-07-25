from datetime import date

def csvFormat(str):
    if str:
        return str.encode('latin-1','ignore')
    else:
        return ""
    
def makeUnicode(str):
    if str:
        try:
            return unicode(str,errors='ignore')
        except:
            return str
    else:
        return ""

def bvFY(d):
    if d.month >= 5:
        return d.year + 1
    else:
        return d.year

def nextMonth(d):
    if d.month == 12:
        return date(d.year + 1, 1, d.day)
    else:
        return date(d.year, d.month + 1, d.day)
    
def dateToDateKey(dateVal):
    return int(str(dateVal.year)+str(dateVal.month).zfill(2)+'01')
