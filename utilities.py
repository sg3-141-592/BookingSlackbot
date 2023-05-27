from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
import pysnooper

# Jinja2 methods
def userHasBooking(bookings, userId):
    for booking in bookings:
        if booking[2] == userId:
            return True
    return False

def numberBookingsRemaining(bookings, numberBookingsAllowed):
    return numberBookingsAllowed - len(bookings)

def truncateString(inputStr: str) -> str:
    if len(inputStr) >= 24:
        inputStr = f"{inputStr[:22]}.."
    return inputStr

def getCurrentTime():
    return int(time.time())

# Get list of the valid booking types for the current enviromment config
@pysnooper.snoop()
def getValidBookings(bookingType, bookingSettings, tzName):
    if bookingType == "DAILY":
        return list(map(lambda x: x.strftime('%Y-%m-%d'), getNextNDays(bookingSettings["numberDaysAdvance"], tzName)))
    elif bookingType == "ONE-OFF":
        bookingDate = datetime.fromtimestamp(bookingSettings["date"], tz=ZoneInfo(tzName))
        currentDateTime = datetime.now(tz=ZoneInfo(tzName))
        if bookingDate >= currentDateTime:
            return [bookingDate]
        else:
            return None
    elif bookingType == "CUSTOM":
        results = []
        for day in getNextNDays(bookingSettings["numberDaysAdvance"], tzName):
            for bookingTime in bookingSettings['bookingTimes']:
                hours, minutes = bookingTime.split(":")
                result = day + timedelta(hours=int(hours), minutes=int(minutes))
                results.append(result.strftime('%Y-%m-%d %H:%M'))
        return results

def databaseResultToDict(input_rows, id):
    # Turn the n-th item to the dictionary key
    result = {}
    for row in input_rows:
        if row[id] in result.keys():
            result[row[id]].append(row)
        else:
            result[row[id]] = [row]
    return result

def getNextNDays(num_days, tzName):
    # Get the set of dates that can be booked in app
    # Using users timezone
    today = datetime.now(ZoneInfo(tzName))
    valid_days = [today]
    for i in range(1, num_days):
        result = today + timedelta(days=i)
        valid_days.append(result.replace(hour=0, minute=0, second=0, microsecond=0))
    return valid_days

def extractBlockIdString(blocks, targetString):
    return list(filter(lambda x: targetString in x, blocks.keys()))[0].replace(targetString, "")
