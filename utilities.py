from datetime import date, timedelta

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

# Get list of the valid booking types for the current enviromment config
def getValidBookings(bookingType, bookingSettings):
    if bookingType == "DAILY":
        return list(map(lambda x: x.strftime('%Y-%m-%d'), getNextNDays(bookingSettings["numberDaysAdvance"])))
    elif bookingType == "ONE-OFF":
        return [bookingSettings["date"]]
    elif bookingType == "CUSTOM":
        results = []
        for day in getNextNDays(bookingSettings["numberDaysAdvance"]):
            for bookingTime in bookingSettings['bookingTimes']:
                results.append(f"{day} {bookingTime}")
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

def getNextNDays(num_days=2):
    # Get the set of dates that can be booked in app
    today = date.today()
    valid_days = [today]
    for i in range(1, num_days):
        valid_days.append(today + timedelta(days=i))
    return valid_days

def extractBlockIdString(blocks, targetString):
    return list(filter(lambda x: targetString in x, blocks.keys()))[0].replace(targetString, "")
