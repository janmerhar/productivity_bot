from cli_args.EventCreateParser import calendar_parser
from gCalExample import calendar
from gcsa.event import Event
from gcsa.google_calendar import GoogleCalendar
from gcsa.reminders import PopupReminder
from datetime import datetime
import parsedatetime as pdt

class CalendarFunctions:
    def __init__(self, calendar):
        self.calendar = calendar
    
    # eventi so object, ki ga lahko prikazem na razlicne nacine
    def printAllEvents(self):
        for event in self.calendar:
            print(type(event.start))

    # def parseArgumets(self, string):
    def createRemindersObject(self, minutes):
        reminders = []
        for i in range(len(minutes)):
            reminders.append(PopupReminder(minutes_before_start=minutes[i]))
        
        return reminders
    
    def createDatetimeObject(self, date):
        pdtCal = pdt.Calendar()
        now = datetime.now()
        
        return pdtCal.parseDT(date, now)

    def createRemindersObject2(self, parsedString):
        if  parsedString["reminders"] is None:
            return None
        reminders = []
        for reminder in parsedString["reminders"][0]:
            reminders.append(PopupReminder(reminder))
        
        return reminders

    def createDatetimeObject2(self, parsedString):
        pdtCal = pdt.Calendar()
        now = datetime.now()

        start = pdtCal.parseDT(" ".join(parsedString["start"][0]), now)[0]
        end = pdtCal.parseDT(" ".join(parsedString["end"][0]), now)[0]
        return [start, end]

    def createDescriptionObject2(self, parsedString):
        return " ".join(parsedString["description"][0]) if parsedString["description"] else None
    
    def eventToObject(self, parsedString):
        eventOptions = parsedString
        eventOptions["reminders"] = self.createRemindersObject2(parsedString)
        eventOptions["start"], eventOptions["end"] = self.createDatetimeObject2(parsedString)
        eventOptions["description"] = self.createDescriptionObject2(parsedString)

        # potrebujem nekje handlanje exceptionov v primeru nepravilnih vnesenih podatkov o eventu
        event = Event(**eventOptions)
        print(eventOptions)
        created_event = self.calendar.add_event(event)
        print(created_event)
        return created_event

if __name__ == "__main__":
    calendar_functions = CalendarFunctions(calendar)
    # calendar_functions.printAllEvents()
    # calendar_functions.createRemindersObject([15, 60, 360])
    # print(calendar.list_event_colors())
    args = calendar_parser.parse_args("-n ime -s thursday 7 am -e thursday 8 am -c 3 -r 1 2 3 -d 123<br/>".split())
    args = vars(args)
    # print(**calendar_functions.eventToObject(args))
    # print(" ".join(args["start"][0]))
    calendar_functions.eventToObject(args)