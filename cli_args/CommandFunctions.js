const path = require("path")

class CommandFunctions {
  static myParseInt(value, dummyPrevious) {
    // parseInt takes a string and an optional radix
    return parseInt(value)
  }
  static joinThings(value, previous) {
    return `${previous || ""} ${value}`.trim()
  }
  static lowerCase(value, dummyPrevious) {
    return value.toLowerCase()
  }
  static fileWithoutExtension(value) {
    if (path.extname(value).length == 0) {
      return value
    } else {
      return value
        .split(".")
        .splice(0, value.split(".").length - 1)
        .join(".")
    }
  }
  static filenameOffDirStructure() {
    const cwd = process.cwd()
    let levels = {
      lvl1: path.basename(cwd),
      lvl2: path.basename(path.resolve(cwd, "..")),
      lvl3: path.basename(path.resolve(cwd, "..", "..")),
    }

    let fileName = "DEFAULT_NAME"
    // priprava za validacijo ali je pravo ime
    // 1. validacija za lvl3
    let regex = /^[A-Ž0-9]+$/
    if (regex.test(levels.lvl3)) {
      // 2. validacija za lvl1
      if (/^[0-9]+$/.test(levels.lvl1.split("_")[0])) {
        if (levels.lvl1.split("_")[1].charAt(0) == levels.lvl2.charAt(0)) {
          fileName = `${levels.lvl1.split("_")[0]}_${levels.lvl3}_${
            levels.lvl1.split("_")[1]
          }`
        }
      }
    }

    // console.log(fileName)
    return fileName
  }
}

module.exports = { CommandFunctions }
