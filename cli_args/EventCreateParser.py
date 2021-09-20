# https://realpython.com/command-line-interfaces-python-argparse/
import argparse

event_create = argparse.ArgumentParser()

# summary == event name
event_create.add_argument("-n",
                          "--name",
                          dest="summary",
                          type=str, 
                          required=True, 
                          help="Summary or event name")
# start of event date/datetime
event_create.add_argument("-s",
                          "--start",
                          action="append",  # i can pass multiple values to thihs flag
                          nargs="+",        # 1 or more argumets
                          required=True, 
                          help="Start of the event in date/datetime")
# end of event date/datetime
event_create.add_argument("-e",
                          "--end",
                          action="append",  # i can pass multiple values to thihs flag
                          nargs="+",        # 1 or more argumets
                          required=True, 
                          help="End of the event in date/datetime")
# color_id of the event color
event_create.add_argument("-c",
                          "--color",
                          dest="color_id",
                          required=True,
                          default=1,
                          help="Color id of the event"
                          )

# event description [optional]
event_create.add_argument("-d", 
                          "--description",
                          action="append",  # i can pass multiple values to thihs flag
                          nargs="+",        # 1 or more argumets
                          help="Description of the event in optional HTML")
# event location [optional]
event_create.add_argument("-l",
                          "--location",
                          help="Location of the event")
# event recurrance [optional]: RRULE|RDATE|EXRULE|EXDATE
# see https://google-calendar-simple-api.readthedocs.io/en/latest/code/recurrence.html#module-gcsa.recurrence
""""
will have to rename the flags
event_parser.add_argument("-r",
                          "--recurrance",
                          dest="recurrance",
                          choices=["RRULE", "RDATE", "EXRULE", "EXDATE"],
                          help="Allows you to set recurrance of the event"
                          )
"""

# event reminders [optional]
# see https://google-calendar-simple-api.readthedocs.io/en/latest/code/reminders.html#module-gcsa.reminders
# TODO tukaj bom moral nekako narediti ukaz za kreiranje remimnderjev
event_create.add_argument("-r",
                          "--reminders",
                          dest="reminders",
                          action="append",  # i can pass multiple values to thihs flag
                          nargs="*",        # 0 or more argumets
                          help="Reminders of the event")

# https://stackoverflow.com/questions/8878478/how-can-i-use-pythons-argparse-with-a-predefined-argument-string
# parsing arguments from string received form Bot
# args = event_parser.parse_args(discordString.split())

if __name__ == "__main__":
    args = event_create.parse_args("-n ime -s zacetek enkrat ze -e konec -c 69".split())
    args = vars(args)
    print(args)