# https://google-calendar-simple-api.readthedocs.io/en/latest/code/google_calendar.html?highlight=get_events#gcsa.google_calendar.GoogleCalendar.get_events
import argparse
"""
get_events(
    time_min=None, [date/datetime]
	time_max=None, [date/datetime]
	order_by=None, ["startTime", "updated"]
	timezone='Etc/UTC',
	single_events=False, [True/False]
	query=None,    [iskanje nizov v katerem koli polju Eventa]
	**kwargs       [Googlove dodatne specifike]
) → Iterable[gcsa.event.Event]
"""
event_get = argparse.ArgumentParser()
