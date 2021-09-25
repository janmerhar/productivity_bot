const { calendar } = require("./cal_connect")

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
}

const calClasses = new CalendarClasses(calendar)
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

module.exports = {
  CalendarClasses,
}
