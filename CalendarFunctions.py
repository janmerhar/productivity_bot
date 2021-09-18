from cli_args.CalendarParser import calendar_parser
from gCalExample import calendar
from gcsa.event import Event
from gcsa.google_calendar import GoogleCalendar
from gcsa.reminders import PopupReminder
from datetime import datetime
import parsedatetime as pdt

class CalendarFunctions:
    def __init__(self, calendar):
        self.calendar = calendar
    
    def printAllEvents(self):
        for event in self.calendar:
            print(event)

    # def parseArgumets(self, string):
    def createRemindersObject(self, minutes):
        reminders = []
        for i in range(len(minutes)):
            reminders.append(PopupReminder(minutes_before_start=minutes[i]))
        
        return reminders
    
    def createDatetimeObject(self, dates):
        pdtCal = pdt.Calendar()
        now = datetime.now()
        datetimes = []
        for date in dates:
            datetimes.append(pdtCal.parseDT(date, now)[0])
        
        return datetimes


if __name__ == "__main__":
    calendar_functions = CalendarFunctions(calendar)
    # calendar_functions.printAllEvents()
    # calendar_functions.createRemindersObject([15, 60, 360])
    # print(calendar.list_event_colors())

    # example of natural language processing
    # cal = pdt.Calendar()
    # print(cal.parseDT("tomorrow evening", datetime.now())[0])