const { calendar } = require("./cal_connect")
const { event_create } = require("../cli_args/cli_event_create")
const { event_query } = require("../cli_args/cli_event_query")

class CalendarClasses {
  constructor(calendar) {
    this.calendar = calendar
  }

  async eventInsert(params) {
    const eventInsert = await calendar.events.insert(params)
    return eventInsert
  }

  async eventList(params) {
    const events = await this.calendar.events.list(params)
    return events
  }

  async calendarList() {
    const calendars = this.calendar.calendarList.list()
    return calendars
  }
  returnCommanderOptions(commanderClass, inputArgs) {
    const argsArray = [
      process.argv[0],
      process.argv[1],
      ...inputArgs.split(" "),
    ]
    commanderClass.parse(argsArray)

    const options = commanderClass.opts()
    return options
  }
}

/*
const calClasses = new CalendarClasses(calendar)
calClasses
  .eventList({
    calendarId: "primary",
    timeMin: new Date(),
    maxResults: 10,
    singleEvents: true,
    orderBy: "startTime",
  })
  .then((res) => {
    console.log(res)
  })
  .catch((err) => {
    console.log(err)
  })
*/

module.exports = { CalendarClasses }
