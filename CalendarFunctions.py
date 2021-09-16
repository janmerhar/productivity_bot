class CalendarFunctions:
    def __init__(self, calendar):
        self.calendar = calendar
    
    def printAllEvents(self):
        for event in self.calendar:
            print(event)