const { calendar } = require("./cal_connect")
const { eventCreate } = require("../cli_args/cli_event_create")
const { eventQuery } = require("../cli_args/cli_event_query")
const chrono = require("chrono-node")

class CalendarClasses {
  constructor(calendar) {
    this.calendar = calendar
  }

  async eventInsert(params) {
    const eventInsert = await this.calendar.events.insert(params)
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

  stringToDatetime(string) {
    const chronoRes = chrono.parse(string)
    const parsedDatetime = chronoRes[0].start.date()

    // returning JS object Date
    return parsedDatetime
  }

  postEvent(argString) {
    let commanderArgs = this.returnCommanderOptions(eventCreate, argString)

    commanderArgs.start = {
      dateTime: this.stringToDatetime(commanderArgs.start),
    }
    commanderArgs.end = {
      dateTime: this.stringToDatetime(commanderArgs.end),
    }
    // manjkajo reminderji
    this.eventInsert({
      calendarId: commanderArgs.calendarId,
      resource: commanderArgs,
    })
      .then(() => console.log("OK"))
      .catch((err) => console.error(err))
  }
}

const calClasses = new CalendarClasses(calendar)

/*
calClasses.postEvent(
  "-n Ime iz CalendarClasses.js -s today 22.30 -e today 23.30 -d Kr tko nekaj da preverim<br>ce dela"
)
*/
/*
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
