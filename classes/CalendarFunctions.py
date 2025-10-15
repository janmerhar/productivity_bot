from gcsa.event import Event
from gcsa.google_calendar import GoogleCalendar
import datetime


class CalendarFunctions():
    def __init__(self, email):
        self.calendar = GoogleCalendar(
            email, credentials_path="credentials.json")

    #
    # Events
    # https://google-calendar-simple-api.readthedocs.io/en/latest/events.html
    #

    #
    # Attendees
    # https://google-calendar-simple-api.readthedocs.io/en/latest/attendees.html
    #
    #
    # Attachments
    # https://google-calendar-simple-api.readthedocs.io/en/latest/attachments.html
    #
    #
    # Conference
    # https://google-calendar-simple-api.readthedocs.io/en/latest/conference.html
    #
    #
    # Recurrence
    # https://google-calendar-simple-api.readthedocs.io/en/latest/recurrence.html
    #
    #
    # Serializers
    # https://google-calendar-simple-api.readthedocs.io/en/latest/serializers.html
    #


if __name__ == '__main__':
    cal = CalendarFunctions("myspdy@gmail.com")
    print(cal.calendar)

    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)

    upcoming_events = cal.calendar.get_events(
        time_min=today, time_max=tomorrow)

    for event in upcoming_events:
        print(event)
