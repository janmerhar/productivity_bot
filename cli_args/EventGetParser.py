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

# start of the search range
event_get.add_argument("-s",
                        "--start",
                        action="append",  
                        nargs="+",        
                        required=True, 
                        help="Start of the search range"
)
# end of the search range
event_get.add_argument("-e",
                        "--end",
                        action="append",  
                        nargs="+",        
                        required=True, 
                        help="End of the search range"
)

# Query that is searched in event fields
event_get.add_argument("-q",
                       "--query",
                       action="append", 
                       nargs="*", 
                       help="Query that is searched in event fields"
)

if __name__ == "__main__":
    args = event_get.parse_args("-s today -e tomorrow -q 1 2 3 4 5 6 7 8 9".split())
    args = vars(args)
    print(args)