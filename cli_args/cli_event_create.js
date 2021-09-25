const { Command } = require("commander")
const { CommandFunctions } = require("./CommandFunctions")

const manipulatorManCommander = new Command()

/*
 * REQUIRED OPTIONS
 */
manipulatorManCommander
  .requiredOption(
    "-n, --summary, --name <strings...>",
    "Summary or event name",
    CommandFunctions.joinThings
  )
  .requiredOption(
    "-s, --start <strings...>",
    "Start of the event in date/datetime",
    CommandFunctions.joinThings
  )
  .requiredOption(
    "-e, --end <strings...>",
    "End of the event in date/datetime",
    CommandFunctions.joinThings
  )
  .requiredOption(
    "-c, --color_id, --color_id <number>",
    "Color id of the event",
    1
  )

/*
 * OPTIONAL OPTIONS
 */
manipulatorManCommander
  .option(
    "-d, --description <strings...>",
    "Description of the event in optional HTML",
    CommandFunctions.joinThings
  )
  .option(
    "-l, --location <strings...>",
    "Location of the event",
    CommandFunctions.joinThings
  )
  /*.option(
    "-r, --recurrance <strings...>",
    "Allows you to set recurrance of the event",
    CommandFunctions.joinThings
  ).choices(["RRULE", "RDATE", "EXRULE", "EXDATE"])
  */ .option(
    "-r, --reminders <strings...>",
    "Reminders of the event",
    CommandFunctions.joinThings
  )

const args =
  "-n Ime eventat -s tomorrow morning -e tomorrow evening -d tvoja mama ima ??? tako kot ga ima tale description"
manipulatorManCommander.parse([
  process.argv[0],
  process.argv[1],
  ...args.split(" "),
])
console.log(manipulatorManCommander.opts())

module.exports = { manipulatorManCommander }
