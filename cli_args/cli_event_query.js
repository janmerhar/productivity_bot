const { Command } = require("commander")
const { CommandFunctions } = require("./CommandFunctions")

const eventQuery = new Command()

/*
 * REQUIRED OPTIONS
 */
eventQuery
  // need default interval
  // i would say current day will do fine
  .requiredOption(
    "-s, --timeMin <strings...>",
    "Start of the query interval in datetime",
    CommandFunctions.joinThings
  )
  .requiredOption(
    "-e, --timeMax <strings...>",
    "End of the query interval in datetime",
    CommandFunctions.joinThings
  )

/*
 * OPTIONAL OPTIONS
 */
eventQuery
  // preferably I want events from ALL calendars
  .option("-cid, --calendarId <string>", "Calendar identifier")
  .option(
    "-r, --maxResults <number>",
    "Maximum number of events returned on one result page",
    10
  )
  .option(
    "-o, --orderBy <string>",
    "The order of the events returned in the result.",
    "startTime"
  )
  // fix this later
  // .choices(["startTime", "updated"])
  .option(
    "-q <strings...>",
    "Query string for mathing in any event field",
    CommandFunctions.joinThings
  )

/*
const args = "-s tomorrow morning -e tomorrow evening -o HEHE"
eventQuery.parse([process.argv[0], process.argv[1], ...args.split(" ")])
console.log(eventQuery.opts())
*/

module.exports = { eventQuery }
