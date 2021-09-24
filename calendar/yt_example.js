const { google } = require("googleapis")
const { OAuth2 } = google.auth
const fs = require("fs")
const { exit } = require("process")

const credentials = JSON.parse(fs.readFileSync("credentials.json", "utf-8"))
const token = JSON.parse(fs.readFileSync("token.json", "utf-8"))

// Create a new instance of oAuth and set our Client ID & Client Secret.
const oAuth2Client = new OAuth2(
  credentials.web.client_id,
  credentials.web.client_secret,
  credentials.web.redirect_uris[0]
)

// Call the setCredentials method on our oAuth2Client instance and set our refresh token.
oAuth2Client.setCredentials({
  refresh_token: token.refresh_token,
})

// Create a new calender instance.
const calendar = google.calendar({ version: "v3", auth: oAuth2Client })

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

calendar.events.insert({ calendarId: "primary", resource: event }, (err) => {
  // Check for errors and log them if they exist.
  if (err) console.error("Error Creating Calender Event:", err)
  // Else log that the event was created.
  else console.log("Calendar event successfully created.")
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
