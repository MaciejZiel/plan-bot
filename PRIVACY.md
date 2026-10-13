# Privacy policy

This policy covers the public plan-bot on Discord (and Telegram) run by Maciej Zieliński
([MaciejZiel](https://github.com/MaciejZiel)). plan-bot shows your university timetable from an
ICS link that you provide. Last updated: 2026-10-13.

## What is stored

For each Discord user who uses the bot:

- your Discord user ID (and, for older installations, the ID of a channel)
- the timetable (ICS) link you subscribed with, or a note that you use the fictional demo
- your language, group filter and reminder, change-alert and weekly-summary settings
- a copy of the classes read from your timetable (subject, time, room, description, groups),
  refreshed about every 30 minutes
- technical bookkeeping: when the feed was last refreshed, the last error, and which reminders
  were already sent (these markers are deleted after two days)

The bot does **not** store the text of your messages, your name, your avatar, your e-mail, your
servers or your DMs. It reads a message only when you write to the bot in a DM or mention it, and
only to decide which command you meant.

Be careful with the link: an ICS link is often a personal secret. Anyone who has it can read your
timetable, and some links reveal your name or student ID. The bot stores it so that it can
refresh your timetable.

## Logs

The server keeps technical logs (errors, command names, counts). User and channel IDs appear only
as a short keyed hash that cannot be reversed without the bot's secret, and bot tokens are
redacted. Logs are rotated on the server.

## How it is used

Only to answer your commands, send the reminders and alerts you switched on, and keep the service
running. Nothing is sold, shared with third parties, used for advertising or used for training
models. The bot does not call any AI or analytics service.

Two parties see data by the nature of the service:

- **Discord** processes your messages and the bot's answers under its own terms and privacy
  policy.
- **The server that hosts your timetable** sees a request from the bot's server when the bot
  downloads your feed. The bot makes only outgoing connections and never logs in to university
  portals.

## Where it lives

On a self-hosted home server run by the owner, in a SQLite database. It is not copied to a cloud
service.

## Retention and deletion

- Data is kept until you delete it. Send `/forget` and everything stored about you (link,
  settings, class copy, reminder markers) is deleted immediately.
- If the bot finds that your account or a registered channel no longer exists, it deletes that
  data automatically.
- If you close your DMs, the bot switches reminders, alerts and summaries off for you but keeps
  your timetable until you use `/forget`.
- Removing the bot from your account or server does not delete your data by itself. Use `/forget`
  first. If you cannot, open an issue (below) with your Discord user ID and it will be deleted.

## Children

The bot is meant for students and is not directed at children under 13, the minimum age Discord
itself requires.

## Contact

Questions or deletion requests: open an issue at
<https://github.com/MaciejZiel/plan-bot/issues>. Do not post your timetable link there. Changes
to this policy are made in this repository and visible in its history.
