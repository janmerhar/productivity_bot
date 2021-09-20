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

class Calendar(commands.Cog):
    def __init__(self, client):
        self.client = client
    
    async def send_reactions(self, msg, reactions):
        for i in range(len(reactions)):
            await msg.add_reaction(reactions[i])

    @commands.command()
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
        embed.add_field(name="non inline name", value="non inline value", inline=False)
        # inline field values
        # maximum 3 inline fields per row
        embed.add_field(name="INLINE NAME1", value="INLINE VALUE1", inline=True)
        embed.add_field(name="INLINE NAME2", value="INLINE VALUE2", inline=True)
        embed.add_field(name="INLINE NAME3", value="INLINE VALUE3", inline=True)
        embed.add_field(name="INLINE NAME4", value="INLINE VALUE4", inline=True)

        embed.set_footer(
            text=f"Footer"
        )
        # print(embed.to_dict())

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
        print(message)

def setup(client):
    client.add_cog(Calendar(client))