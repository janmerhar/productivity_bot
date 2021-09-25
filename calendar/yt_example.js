const { google } = require("googleapis")
const { calendar } = require("./cal_connect")

// Create a new event start date instance for temp uses in our calendar.
const eventStartTime = new Date()

// Create a new event end date instance for temp uses in our calendar.
const eventEndTime = new Date()
eventEndTime.setMinutes(eventEndTime.getMinutes() + 45)

// Create a dummy event for temp uses in our calendar
const event = {
  summary: `Meeting with David`,
  location: `3595 California St, San Francisco, CA 94118`,
  description: `Meet with David to talk about the new client project and how to integrate the calendar for booking.`,
  colorId: 1,
  start: {
    dateTime: eventStartTime,
  },
  end: {
    dateTime: eventEndTime,
  },
}

/*
calendar.events.insert({ calendarId: "primary", resource: event }, (err) => {
  // Check for errors and log them if they exist.
  if (err) console.error("Error Creating Calender Event:", err)
  // Else log that the event was created.
  else console.log("Calendar event successfully created.")
})
*/

const insert = async (calendar, params) => {
  const eventInsert = await calendar.events.insert(params)
  // console.log(eventInsert)
  return eventInsert
}
/*
calendar.events
  .insert({ calendarId: "primary", resource: event })
  .then(() => console.log("OK"))
  .catch("Ni OK")
/*
/*
insert(calendar, { calendarId: "primary", resource: event })
  .then(() => {
    console.log("Calendar OK")
  })
  .catch((err) => {
    console.log("Ne dela")
  })
*/

const listEvents = (calendar, params) => {
  calendar.events
    .list(params)
    .then((res) => {
      const events = res.data.items
      if (events.length) {
        console.log("Upcoming 10 events:")
        events.map((event, i) => {
          const start = event.start.dateTime || event.start.date
          console.log(`${start} - ${event.summary}`)
        })
      } else {
        console.log("No upcoming events found.")
      }
    })
    .catch((err) => {
      console.log(err)
    })
}

listEvents(calendar, {
  calendarId: "primary",
  timeMin: new Date(),
  maxResults: 10,
  singleEvents: true,
  orderBy: "startTime",
})

/*
// Check if we a busy and have an event on our calendar for the same time.
calendar.freebusy.query(
  {
    resource: {
      timeMin: eventStartTime,
      timeMax: eventEndTime,
      items: [{ id: "primary" }],
    },
  },
  (err, res) => {
    // Check for errors in our query and log them if they exist.
    if (err) return console.error("Free Busy Query Error: ", err)

    // Create an array of all events on our calendar during that time.
    const eventArr = res.data.calendars.primary.busy

    // Check if event array is empty which means we are not busy
    if (eventArr.length === 0)
      // If we are not busy create a new calendar event.
      return calendar.events.insert(
        { calendarId: "primary", resource: event },
        (err) => {
          // Check for errors and log them if they exist.
          if (err) return console.error("Error Creating Calender Event:", err)
          // Else log that the event was created.
          return console.log("Calendar event successfully created.")
        }
      )

    // If event array is not empty log that we are busy.
    return console.log(`Sorry I'm busy...`)
  }
)

*/
