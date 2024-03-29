from cli_args.EventCreateParser import event_create
from cli_args.EventGetParser import event_get
from gCalExample import calendar
from gcsa.event import Event
from gcsa.google_calendar import GoogleCalendar
from gcsa.reminders import PopupReminder
from datetime import datetime
import parsedatetime as pdt


class CalendarFunctionsOLD:
    def __init__(self, calendar):
        self.calendar = calendar

    # eventi so object, ki ga lahko prikazem na razlicne nacine
    def printAllEvents(self):
        for event in self.calendar:
            print(type(event.start))

    def createRemindersObject2(self, parsedString):
        if parsedString["reminders"] is None:
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

    def prettyDatetime(self, datetimeObject):
        return datetimeObject.strftime("%d. %m. %Y %H:%M")

    def eventToObject(self, parsedString):
        eventOptions = parsedString
        eventOptions["summary"] = " ".join(parsedString["summary"][0])
        eventOptions["reminders"] = self.createRemindersObject2(parsedString)
        eventOptions["start"], eventOptions["end"] = self.createDatetimeObject2(
            parsedString)
        # tale ne deluje pravilno za vec besedne stringe
        eventOptions["description"] = self.createDescriptionObject2(
            parsedString)

        # potrebujem nekje handlanje exceptionov v primeru nepravilnih vnesenih podatkov o eventu
        event = Event(**eventOptions)
        # print(eventOptions)
        created_event = self.calendar.add_event(event)
        return created_event

    # def
