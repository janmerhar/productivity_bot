# Pomodoro Voice Assets

Place the local-only Pomodoro audio files here:

- `focus.mp3`
- `break.mp3`

These MP3 files are intentionally ignored by git. Docker Compose mounts this
directory into the container at `/app/assets`, matching the default runtime paths
used by the bot.
