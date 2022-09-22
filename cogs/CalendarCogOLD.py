import discord
from discord.ext import commands
import datetime
import json
import os
import platform
import random
import sys
import aiohttp
# import Google Calendar library
from gcsa.event import Event
from gcsa.google_calendar import GoogleCalendar
from gcsa.recurrence import Recurrence, DAILY, SU, SA
from beautiful_date import *
# importing Classes folder
from Classes.CalendarFunctions import CalendarFunctions
# importing cli_args folder
from cli_args.EventCreateParser import event_create
from cli_args.EventGetParser import event_get

calendar = GoogleCalendar('myspdy@gmail.com')
cfunctions = CalendarFunctions(calendar)


class CalendarOLD(commands.Cog):
    def __init__(self, client):
        self.client = client

    async def send_reactions(self, msg, reactions):
        for i in range(len(reactions)):
            await msg.add_reaction(reactions[i])

    @commands.command(aliases=["embed"])
    async def cal(self, ctx):
        server = ctx.message.guild
        time = str(server.created_at)
        time = time.split(" ")
        time = time[0]

        embed = discord.Embed(
            title=":date: Google Calendar",
            description="Embed discription",
            color=0x4086f4
        )
        embed.set_thumbnail(
            url="https://ssl.gstatic.com/calendar/images/dynamiclogo_2020q4/calendar_17_2x.png"
        )

        # non inline field
        embed.add_field(name="non inline name",
                        value="non inline value", inline=False)
        # inline field values
        # maximum 3 inline fields per row
        embed.add_field(name="INLINE NAME1",
                        value="INLINE VALUE1", inline=True)
        embed.add_field(name="INLINE NAME2",
                        value="INLINE VALUE2", inline=True)
        embed.add_field(name="INLINE NAME3",
                        value="INLINE VALUE3", inline=True)
        embed.add_field(name="INLINE NAME4",
                        value="INLINE VALUE4", inline=True)

        embed.set_footer(
            text=f"Footer"
        )
        print(embed.to_dict())

        # adding reactions on message
        msg = await ctx.send(embed=embed)

        # sending reactions to the message
        await self.send_reactions(msg, ["💖", "🇦", "🇧", "🇨", "🇩", "🇪"])

    @commands.command()
    async def colors(self):
        # prikazem vse barve, ki so na voljo
        # pri izbiri za vnos na koledar
        return

    @commands.command()
    async def all_events(self):
        embed = discord.Embed(
            title=":date: Google Calendar",
            description="Embed discription",
            color=0x4086f4
        )
        embed.set_thumbnail(
            url="https://ssl.gstatic.com/calendar/images/dynamiclogo_2020q4/calendar_17_2x.png"
        )

    @commands.command(aliases=["cal-event"])
    async def cal_event(self, ctx, *received_message):
        message = " ".join(received_message)

        args = vars(event_create.parse_args(message.split()))
        created_event = cfunctions.eventToObject(args)

        embed = discord.Embed(
            title=":white_check_mark: Event added", description="", color=0x4086f4)
        embed.set_thumbnail(
            url="https://ssl.gstatic.com/calendar/images/dynamiclogo_2020q4/calendar_17_2x.png")
        embed.set_footer(text="Google Calendar Event")
        # adding fields about event
        embed.add_field(name="Event name",
                        value=created_event.summary, inline=False)
        embed.add_field(name="Start", value=cfunctions.prettyDatetime(
            created_event.start), inline=True)
        embed.add_field(name="End", value=cfunctions.prettyDatetime(
            created_event.end), inline=True)
        embed.add_field(
            name="Description", value=created_event.description if created_event.description else "[no description]", inline=False)
        # reminders
        if len(created_event.reminders) == 0:
            embed.add_field(name=" -- Reminders -- ",
                            value="[no reminders]", inline=False)
        else:
            embed.add_field(name=" -- Reminders -- ",
                            value=f"{len(created_event.reminders)} reminders", inline=False)
            # loop behaves strange
            for i in range(0, len(created_event.reminders)):
                index = i + 1
                embed.add_field(name=f"reminder {index}", value=str(
                    created_event.reminders[i].minutes_before_start) + " min", inline=True)

        await ctx.send(embed=embed)


def setup(client):
    client.add_cog(Calendar(client))
