const { google } = require("googleapis")
const { OAuth2 } = google.auth
const fs = require("fs")

const credentials = JSON.parse(fs.readFileSync("credentials.json", "utf-8"))
const token = JSON.parse(fs.readFileSync("token.json", "utf-8"))

const auth = new OAuth2(
  credentials.web.client_id,
  credentials.web.client_secret,
  credentials.web.redirect_uris[0]
)

auth.setCredentials({
  refresh_token: token.refresh_token,
})

const calendar = google.calendar({ version: "v3", auth: auth })

module.exports = {
  calendar,
  auth,
}
