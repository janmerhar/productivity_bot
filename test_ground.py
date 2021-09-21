from Classes.CalendarFunctions import CalendarFunctions
from cli_args.EventCreateParser import event_create
from cli_args.EventGetParser import event_get
from gcsa.google_calendar import GoogleCalendar
from datetime import datetime

calendar = GoogleCalendar('myspdy@gmail.com')
cfunctions = CalendarFunctions(calendar)
# calendar_functions.printAllEvents()
# print(calendar.list_event_colors())
args = event_create.parse_args("-n ime -s thursday 7 am -e thursday 8 am -c 3 -r 1 2 3 -d 123<br/>".split())
args = vars(args)
# calendar_functions.eventToObject(args)
print(cfunctions.prettyDatetime(datetime.now()))