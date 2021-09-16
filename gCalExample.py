# https://github.com/kuzmoyev/google-calendar-simple-api
from gcsa.event import Event
from gcsa.google_calendar import GoogleCalendar
from gcsa.recurrence import Recurrence, DAILY, SU, SA
from beautiful_date import *

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
    from datetime import date
    calendar.get_events(
        # start_date=date.today(),
        # start_date=(17 / Sept / 2021)[0:00],
        # end_date=(16 / Sept / 2021)[0:00],
    )
    print(calendar)
    for event in calendar:
        print(event)