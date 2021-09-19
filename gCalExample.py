# https://github.com/kuzmoyev/google-calendar-simple-api
from gcsa.event import Event
from gcsa.google_calendar import GoogleCalendar
from gcsa.recurrence import Recurrence, DAILY, SU, SA
from beautiful_date import *
import datetime

calendar = GoogleCalendar('myspdy@gmail.com')

""""
Create recurring event
event = Event(
'Breakfast',
start=(1 / Jan / 2019)[9:00],
recurrence=[
    Recurrence.rule(freq=DAILY),
    Recurrence.exclude_rule(by_week_day=[SU, SA]),
    Recurrence.exclude_times([
        (19 / Apr / 2019)[9:00],
        (22 / Apr / 2019)[9:00]
    ])
],
minutes_before_email_reminder=50
)
calendar.add_event(event)
"""
"""
Print all events fetched
"""
if __name__ == "__main__":
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)

    upcoming_events = calendar.get_events(time_min=today, time_max=tomorrow)

    for event in upcoming_events:
        print(event)