import datetime
from typing import Dict, Optional
import discord
from discord.ext import commands
from discord import app_commands
from classes.UserSettingsFunctions import UserSettingsFunctions
from classes.TogglFunctions import TogglFunctions
from abstract.EmbedsAbstract import EmbedsAbstract
from services.toggl_time_entry_service import TogglTimeEntryService


class TogglEmbeds(EmbedsAbstract):
    MAX_EMBEDS_PER_MESSAGE = 10
    MAX_EMBED_DESCRIPTION = 4096

    @staticmethod
    def _get_toggl(
        guild_id: Optional[int],
        user_id: Optional[int],
    ) -> Optional[TogglFunctions]:
        del guild_id
        if user_id is None:
            return None
        api_key = UserSettingsFunctions.get_toggl_api_key(user_id)
        if not api_key:
            return None
        workspace_id = UserSettingsFunctions.get_toggl_workspace_id(user_id)
        toggl = TogglFunctions(api_key, workspace_id=workspace_id)
        if workspace_id is None:
            resolved_workspace_id = toggl.workspace_id
            if resolved_workspace_id is not None:
                try:
                    UserSettingsFunctions.set_toggl_workspace_id(
                        user_id,
                        resolved_workspace_id,
                    )
                except Exception:
                    pass
        return toggl

    @staticmethod
    def _missing_key_embed() -> dict:
        embed = discord.Embed(
            title=":stopwatch: Toggl",
            color=discord.Colour.from_str("#552d4f"),
            description="Run any Toggl command and provide your API key in the popup.",
        )
        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
        return {"embeds": [embed]}

    @staticmethod
    def _format_discord_datetime(
        value: object,
        *,
        style: str = "F",
    ) -> Optional[str]:
        if not value:
            return None

        if isinstance(value, datetime.datetime):
            parsed = value
        else:
            raw_value = str(value).strip()
            if not raw_value:
                return None
            try:
                parsed = datetime.datetime.fromisoformat(
                    raw_value.replace("Z", "+00:00")
                )
            except ValueError:
                return raw_value

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)

        return f"<t:{int(parsed.timestamp())}:{style}>"

    @staticmethod
    def _format_timer_timestamp(value: object) -> Optional[str]:
        formatted_relative = TogglEmbeds._format_discord_datetime(value, style="R")

        return formatted_relative or (
            str(value).strip() if value is not None else None
        )

    @staticmethod
    def _get_time_entry_project(
        toggl: TogglFunctions,
        timer_data: Optional[dict],
    ) -> Optional[dict]:
        if not timer_data:
            return None

        workspace_id = timer_data.get("workspace_id") or timer_data.get("wid")
        project_id = timer_data.get("project_id") or timer_data.get("pid")

        if workspace_id is None or project_id is None:
            return None

        return toggl.getProjectById(
            workspace_id=workspace_id,
            project_id=project_id,
        )

    @staticmethod
    def _format_time_entry_started(timer_data: Optional[dict]) -> Optional[str]:
        if not timer_data:
            return None

        return TogglEmbeds._format_timer_timestamp(timer_data.get("start"))

    @staticmethod
    def _format_billable(value: object) -> str:
        if value is True:
            return "Yes"
        if value is False:
            return "No"
        return "Not set"

    @staticmethod
    def _format_tags(tags: object) -> str:
        if not isinstance(tags, list):
            return "None"

        cleaned_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
        if not cleaned_tags:
            return "None"

        return ", ".join(cleaned_tags)

    @staticmethod
    def _single_timer_embed(
        title: str,
        toggl: TogglFunctions,
        timer_data: dict,
        *,
        description: Optional[str] = None,
        project_data: Optional[dict] = None,
        color: Optional[str] = None,
        fallback_color: str = "#df80c7",
    ) -> discord.Embed:
        resolved_project = project_data or TogglEmbeds._get_time_entry_project(
            toggl,
            timer_data,
        )
        resolved_color = color or (
            resolved_project.get("color")
            if resolved_project is not None and resolved_project.get("color")
            else fallback_color
        )

        embed = discord.Embed(
            title=title,
            color=discord.Colour.from_str(resolved_color),
            description=description,
        )
        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
        embed.add_field(
            name="Description",
            value=timer_data.get("description") or "No description",
            inline=False,
        )
        embed.add_field(
            name="Project",
            value=(
                resolved_project.get("name")
                if resolved_project is not None and resolved_project.get("name")
                else "No project"
            ),
            inline=False,
        )
        embed.add_field(
            name="Billable",
            value=TogglEmbeds._format_billable(timer_data.get("billable")),
            inline=False,
        )
        embed.add_field(
            name="Tags",
            value=TogglEmbeds._format_tags(timer_data.get("tags")),
            inline=False,
        )
        embed.add_field(
            name="Start",
            value=TogglEmbeds._format_time_entry_started(timer_data) or "Unknown",
            inline=False,
        )

        return embed

    @staticmethod
    def _single_timer_payload(
        *,
        embed: discord.Embed,
        guild_id: Optional[int],
        user_id: int,
        timer_data: dict,
        is_active: bool,
    ) -> dict:
        return {
            "embeds": [embed],
            "_toggl_timer_view": {
                "guild_id": guild_id,
                "user_id": user_id,
                "timer_data": timer_data,
                "is_active": is_active,
            },
        }

    @staticmethod
    def _active_timer_conflict_embed(
        title: str,
        toggl: TogglFunctions,
        timer_data: dict,
        *,
        guild_id: Optional[int],
        user_id: int,
    ) -> dict:
        embed = TogglEmbeds._single_timer_embed(
            title=title,
            toggl=toggl,
            timer_data=timer_data,
            description=(
                "A Toggl timer is already running. "
                "Use `/toggl timer stop` to end it, then try again."
            ),
            color="#c96a40",
        )

        return TogglEmbeds._single_timer_payload(
            embed=embed,
            guild_id=guild_id,
            user_id=user_id,
            timer_data=timer_data,
            is_active=True,
        )

    @staticmethod
    def _tag_embed(tag: dict, fallback_name: str) -> dict:
        embed = discord.Embed(
            title=":stopwatch: Toggl Tag",
            color=discord.Colour.from_str("#552d4f"),
            description=tag.get("name") or fallback_name,
        )
        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
        embed.add_field(name="Tag ID", value=tag["id"], inline=False)

        created_at = TogglEmbeds._format_discord_datetime(tag.get("at"))
        if created_at:
            embed.add_field(name="Created at", value=created_at, inline=False)

        return {"embeds": [embed]}

    @staticmethod
    def _build_line_embeds(
        *,
        title: str,
        lines: list[str],
        empty_description: str,
        color: str = "#552d4f",
    ) -> list[discord.Embed]:
        if not lines:
            embed = discord.Embed(
                title=title,
                color=discord.Colour.from_str(color),
                description=empty_description,
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
            return [embed]

        embeds: list[discord.Embed] = []
        current_lines: list[str] = []
        current_length = 0

        for line in lines:
            line_length = len(line) + (1 if current_lines else 0)
            if (
                current_lines
                and current_length + line_length
                > TogglEmbeds.MAX_EMBED_DESCRIPTION
            ):
                embed = discord.Embed(
                    title=title,
                    color=discord.Colour.from_str(color),
                    description="\n".join(current_lines),
                )
                embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
                embeds.append(embed)
                if len(embeds) >= TogglEmbeds.MAX_EMBEDS_PER_MESSAGE:
                    break
                current_lines = [line]
                current_length = len(line)
            else:
                current_lines.append(line)
                current_length += line_length

        if (
            current_lines
            and len(embeds) < TogglEmbeds.MAX_EMBEDS_PER_MESSAGE
        ):
            embed = discord.Embed(
                title=title,
                color=discord.Colour.from_str(color),
                description="\n".join(current_lines),
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
            embeds.append(embed)

        total_embeds = len(embeds)
        for index, embed in enumerate(embeds, start=1):
            if total_embeds > 1:
                embed.set_footer(text=f"Page {index}/{total_embeds}")

        if len(embeds) >= TogglEmbeds.MAX_EMBEDS_PER_MESSAGE and len(lines) > sum(
            len(embed.description.splitlines()) for embed in embeds if embed.description
        ):
            last_embed = embeds[-1]
            suffix = "\n… truncated"
            description = last_embed.description or ""
            if len(description) + len(suffix) <= TogglEmbeds.MAX_EMBED_DESCRIPTION:
                last_embed.description = f"{description}{suffix}"

        return embeds

    @staticmethod
    def _format_duration(seconds: int) -> str:
        total_seconds = max(0, int(seconds))
        minutes, sec = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)

        parts: list[str] = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if sec or not parts:
            parts.append(f"{sec}s")

        return " ".join(parts)

    @staticmethod
    def _get_function_by_name(name: str):
        if not name:
            return None
        cleaned = " ".join(str(name).strip().lower().split())
        if cleaned.startswith("toggl "):
            cleaned = cleaned[len("toggl ") :].strip()
        alias_map = {
            "about": "aboutme",
            "account": "aboutme",
            "key clear": "togglkeyclear",
            "tag add": "addtags",
            "tag show": "showtag",
            "timer start": "start",
            "timer stop": "stop",
            "timer current": "timer",
            "timer insert": "inserttimer",
            "timer history": "timerhistory",
            "saved create": "savetimer",
            "saved delete": "removetimer",
            "saved start": "startsaved",
            "saved popular": "populartimers",
            "project create": "newproject",
            "project list": "workspaceprojects",
            "project get": "getproject",
            "alias create": "createalias",
        }
        if cleaned in alias_map:
            cleaned = alias_map[cleaned]
        elif " " in cleaned:
            return None
        try:
            return getattr(TogglEmbeds, f"{cleaned}_embed")
        except AttributeError:
            return None

    #
    # Authentication
    #

    @staticmethod
    def aboutme_embed(guild_id: int, user_id: int) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        data = toggl.aboutMe()

        embed = discord.Embed(title=":stopwatch: Toggl Account", color=0xDF80C7)
        embed.set_thumbnail(url="https://assets.track.toggl.com/images/profile.png")

        embed.add_field(name="ID", value=data["id"], inline=False)
        embed.add_field(name="Email", value=data["email"], inline=False)
        embed.add_field(name="Full name", value=data["fullname"], inline=False)

        embed.add_field(name="Timezone", value=data["timezone"], inline=False)
        registration_date = TogglEmbeds._format_discord_datetime(
            data.get("created_at"),
            style="D",
        )
        if registration_date:
            embed.add_field(
                name="Registration date", value=registration_date, inline=False
            )
        embed.add_field(
            name="Default workspace ID",
            value=data["default_workspace_id"],
            inline=False,
        )

        return {"embed": embed}

    #
    # Tracking
    #

    @staticmethod
    def timer_embed(guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        timer_data = toggl.getCurrentTimeEntry()

        if timer_data is not None:
            embed = TogglEmbeds._single_timer_embed(
                title=":stopwatch: Toggl Current Timer",
                toggl=toggl,
                timer_data=timer_data,
            )
            return TogglEmbeds._single_timer_payload(
                embed=embed,
                guild_id=guild_id,
                user_id=user_id,
                timer_data=timer_data,
                is_active=True,
            )
        else:
            embed = discord.Embed(
                title=":stopwatch: Toggl Current Timer",
                color=discord.Colour.from_str("#df80c7"),
                description="No active timer",
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            return {"embeds": [embed]}

    """
    - Add check if project color is not defined
    """

    @staticmethod
    def start_embed(
        guild_id: int,
        user_id: int,
        project: str = None,
        description: str = None,
        tags: str = None,
        billable=None,
    ) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        curr_timer = toggl.getCurrentTimeEntry()
        normalized_tags = TogglTimeEntryService.parse_tags(tags)
        normalized_billable = TogglTimeEntryService.normalize_billable(billable)

        project_data = None

        if curr_timer is not None:
            return TogglEmbeds._active_timer_conflict_embed(
                title=":stopwatch: Toggl Start Timer",
                toggl=toggl,
                timer_data=curr_timer,
                guild_id=guild_id,
                user_id=user_id,
            )

        workspace_id = toggl.workspace_id
        if workspace_id is None:
            raise ValueError("Could not determine your Toggl workspace.")

        if project is not None:
            project_data = toggl.getProject(
                identifier=project,
                workspace_id=workspace_id,
            )
            if project_data is None:
                raise ValueError("No Toggl project matched that `project` value.")

            new_time = toggl.startCurrentTimeEntry(
                workspace_id,
                billable=normalized_billable,
                description=description,
                pid=project_data["id"] if project_data is not None else None,
                tags=normalized_tags,
            )
        else:
            new_time = toggl.startCurrentTimeEntry(
                workspace_id,
                billable=normalized_billable,
                description=description,
                tags=normalized_tags,
            )

        if not isinstance(new_time, dict) or new_time.get("id") is None:
            raise ValueError("Toggl rejected that timer start request.")

        embed = TogglEmbeds._single_timer_embed(
            title=":stopwatch: Toggl Start Timer",
            toggl=toggl,
            timer_data=new_time,
            project_data=project_data,
        )

        return TogglEmbeds._single_timer_payload(
            embed=embed,
            guild_id=guild_id,
            user_id=user_id,
            timer_data=new_time,
            is_active=True,
        )

    """
    - Stops the timer but does not send embed back
    """

    @staticmethod
    def stop_embed(guild_id: int, user_id: int) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        timer_data = toggl.getCurrentTimeEntry()

        # Already stopped timer
        if timer_data is None:
            description = "No timer running"
        # Timer to be stopped
        else:
            description = "Timer stopped"

        embed = discord.Embed(
            title=":stopwatch: Toggl Stop Timer",
            color=discord.Colour.from_str("#552d4f"),
            description=description,
        )

        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        if timer_data is not None:
            toggl.stopCurrentTimeEntry()
            embed = TogglEmbeds._single_timer_embed(
                title=":stopwatch: Toggl Stop Timer",
                toggl=toggl,
                timer_data=timer_data,
                description=description,
                color="#552d4f",
            )
            return TogglEmbeds._single_timer_payload(
                embed=embed,
                guild_id=guild_id,
                user_id=user_id,
                timer_data=timer_data,
                is_active=False,
            )

        return {"embed": embed}

    @staticmethod
    def tag_embed(
        guild_id: int,
        user_id: int,
        *,
        name: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()

        cleaned_name = str(name or "").strip()
        cleaned_tag = str(tag or "").strip()

        if bool(cleaned_name) == bool(cleaned_tag):
            raise ValueError("Provide exactly one of `name` or `tag`.")

        if cleaned_name:
            created_tag = toggl.createTag(toggl.workspace_id, cleaned_name)
            if not isinstance(created_tag, dict) or created_tag.get("id") is None:
                raise ValueError("Toggl rejected that tag creation request.")
            return TogglEmbeds._tag_embed(created_tag, cleaned_name)

        selected_tag = toggl.getTag(cleaned_tag, toggl.workspace_id)
        if selected_tag is None:
            raise ValueError("No Toggl tag matched that `tag` value.")

        return TogglEmbeds._tag_embed(selected_tag, "Unnamed tag")

    @staticmethod
    def tag_autocomplete_embed(
        current: str,
        guild_id: int,
        user_id: int,
    ) -> list[app_commands.Choice[str]]:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return []

        tags = toggl.findTagsLike(
            identifier=current,
            workspace_id=toggl.workspace_id,
            limit=25,
        )

        choices: list[app_commands.Choice[str]] = []
        for tag in tags:
            tag_id = tag.get("id")
            tag_name = str(tag.get("name") or "").strip()
            if tag_id is None or not tag_name:
                continue

            label = f"{tag_name} | #{tag_id}"
            choices.append(
                app_commands.Choice(
                    name=label[:100],
                    value=tag_name,
                )
            )

        return choices

    @staticmethod
    def inserttimer_embed(
        guild_id: int,
        user_id: int,
        start: str,
        stop: str,
        project: str = None,
        description: str = None,
        tags: str = None,
        billable=None,
        locale_code: Optional[str] = None,
    ) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()

        workspace_id = toggl.workspace_id
        project_data = None
        project_id = None
        if project is not None:
            project_data = toggl.getProject(project, workspace_id=workspace_id)
            if project_data is None:
                raise ValueError("No Toggl project matched that `project` value.")
            project_id = project_data.get("id")

        timezone = UserSettingsFunctions.get_timezone(user_id)
        parsed_range = TogglTimeEntryService.parse_insert_range(
            start,
            stop,
            timezone=timezone,
            locale_code=locale_code,
        )
        normalized_tags = TogglTimeEntryService.parse_tags(tags)
        normalized_billable = TogglTimeEntryService.normalize_billable(billable)

        inserted = toggl.insertTimeEntry(
            workspace_id=workspace_id,
            billable=normalized_billable,
            created_with="productivity_bot",
            description=description,
            duration=parsed_range.duration_seconds,
            pid=project_id,
            project_id=project_id,
            start=TogglTimeEntryService.to_toggl_timestamp(parsed_range.start),
            stop=TogglTimeEntryService.to_toggl_timestamp(parsed_range.stop),
            tags=normalized_tags,
        )

        if not isinstance(inserted, dict) or inserted.get("id") is None:
            raise ValueError("Toggl rejected that timer insert request.")

        embed = TogglEmbeds._single_timer_embed(
            title=":stopwatch: Toggl Insert Timer",
            toggl=toggl,
            timer_data=inserted,
            description=description or "Inserted past timer.",
            project_data=project_data,
            fallback_color="#552d4f",
        )
        embed.add_field(
            name="Stop",
            value=TogglEmbeds._format_timer_timestamp(inserted.get("stop")) or "Unknown",
            inline=False,
        )
        embed.add_field(
            name="Duration",
            value=TogglEmbeds._format_duration(inserted.get("duration", 0)),
            inline=False,
        )

        return {"embeds": [embed]}

    #
    # Saved timers
    # mongoDB
    #

    """
    - Add project color of embed, if applicable
    """

    @staticmethod
    def savetimer_embed(
        guild_id: int,
        user_id: int,
        command: str,
        workspace_id: int = None,
        billable: str = None,
        description: str = None,
        project: str = None,
        tags: str = None,
        tid: int = None,
    ):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()

        inserted_id = toggl.saveTimer(
            guild_id=guild_id,
            user_id=user_id,
            command=command,
            workspace_id=workspace_id,
            billable=billable,
            description=description,
            project=project,
            tid=tid,
        )

        timer = toggl.findSavedTimer(inserted_id, guild_id, user_id)

        embed = discord.Embed(
            title=":stopwatch: Toggl Insert Timer",
            color=discord.Colour.from_str("#552d4f"),
        )

        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        embed.add_field(name="Timer command", value=timer["command"], inline=False)
        embed.add_field(name="Project ID", value=timer["param"]["pid"], inline=False)
        embed.add_field(
            name="Timer description", value=timer["param"]["description"], inline=False
        )

        return {"embeds": [embed]}

    @staticmethod
    def removetimer_embed(identifier: str, guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        timer = toggl.findSavedTimer(identifier, guild_id, user_id)

        if timer is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl Delete Timer",
                color=discord.Colour.from_str("#552d4f"),
                description="Timer not found",
            )

            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            return {"embeds": [embed]}
        else:
            toggl.removeSavedTimer(identifier, guild_id, user_id)

            embed = discord.Embed(
                title=":stopwatch: Toggl Delete Timer",
                color=discord.Colour.from_str("#552d4f"),
                description=f"Timer {timer['command']} deleted",
            )

            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            embed.add_field(name="Timer command", value=timer["command"], inline=False)
            embed.add_field(
                name="Project ID", value=timer["param"]["pid"], inline=False
            )
            embed.add_field(
                name="Timer description",
                value=timer["param"]["description"],
                inline=False,
            )

            return {"embeds": [embed]}

    """
    - TogglFunctions.py/startSavedTimer does not start timer given by Id
    - Active timer will be stopped regardless if the saved command exist in database
    """

    @staticmethod
    def startsaved_embed(identifier: str, guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()

        active_timer = toggl.getCurrentTimeEntry()

        if active_timer is not None:
            return TogglEmbeds._active_timer_conflict_embed(
                title=":stopwatch: Toggl Start Saved Timer",
                toggl=toggl,
                timer_data=active_timer,
                guild_id=guild_id,
                user_id=user_id,
            )

        timer = toggl.startSavedTimer(identifier, guild_id, user_id)

        if timer is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl Start Saved Timer",
                color=discord.Colour.from_str("#552d4f"),
                description="Timer not found",
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            return {"embeds": [embed]}
        else:
            if not isinstance(timer, dict) or timer.get("id") is None:
                raise ValueError("Toggl rejected that saved timer start request.")

            embed = TogglEmbeds._single_timer_embed(
                title=":stopwatch: Toggl Start Saved Timer",
                toggl=toggl,
                timer_data=timer,
            )
            return TogglEmbeds._single_timer_payload(
                embed=embed,
                guild_id=guild_id,
                user_id=user_id,
                timer_data=timer,
                is_active=True,
            )

    @staticmethod
    def startsaved_autocomplete_embed(
        current: str,
        guild_id: int,
        user_id: int,
    ):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return []
        res = [
            app_commands.Choice(name=timer["command"], value=timer["command"])
            for timer in toggl.findSavedTimersLike(
                current,
                guild_id,
                user_id,
            )
        ]

        return res

    @staticmethod
    def populartimers_embed(n: int, guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        timers = toggl.mostCommonlyUsedTimers(n, guild_id, user_id)

        embed = discord.Embed(
            title=":stopwatch: Toggl Stop Timer",
            color=discord.Colour.from_str("#552d4f"),
            description=f"{len(timers)} most commonly used timers",
        )

        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        for timer in timers:
            embed.add_field(name="Command", value=timer["command"], inline=True)
            embed.add_field(name="Project ID", value=timer["param"]["pid"], inline=True)
            embed.add_field(
                name="Description", value=timer["param"]["description"], inline=True
            )

        return {"embeds": [embed]}

    """
    - Function is configured for only this days' timerrs to be displayed,
    otherwise it fails
    """

    @staticmethod
    def timerhistory_embed(n: int, guild_id: int, user_id: int) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        history = toggl.getLastNTimeEntryHistory(n)

        embed = discord.Embed(
            title=":stopwatch: Toggl Timer History",
            color=discord.Colour.from_str("#552d4f"),
            description=f"Last {n} timers",
        )

        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        for timer in history:
            workspace_id = timer.get("workspace_id") or timer.get("wid")
            project_id = timer.get("project_id") or timer.get("pid")
            project_data = None
            if workspace_id is not None and project_id is not None:
                project_data = toggl.getProjectById(
                    workspace_id=workspace_id,
                    project_id=project_id,
                )

            project_name = str((project_data or {}).get("name") or "").strip()
            project = project_name or "<no project>"

            description = str(timer.get("description") or "").strip()
            name = description or "<no description>"

            duration_raw = timer.get("duration") or 0
            try:
                duration_seconds = abs(int(duration_raw))
            except (TypeError, ValueError):
                duration_seconds = 0
            duration = TogglEmbeds._format_duration(duration_seconds)

            embed.add_field(name="Project", value=project, inline=True)
            embed.add_field(name="Name", value=name, inline=True)
            embed.add_field(name="Duration", value=duration, inline=True)

        return {"embeds": [embed]}

    #
    # Projects
    #

    """
    - Add more arguments to be passed in slash command
        -> workspace_id, name, active=True, auto_estimates=None, billable=None,
                      color=None, currency="EUR", estimated_hours=1, is_private=None, template=None 
    """

    @staticmethod
    def _build_project_details_embed(
        project_data: dict,
        *,
        actual_hours: Optional[object] = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=":stopwatch: Toggl Project Details",
            color=discord.Colour.from_str(project_data.get("color") or "#552d4f"),
            description=project_data.get("name") or "Unnamed project",
        )
        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
        embed.add_field(name="Project ID", value=project_data["id"], inline=True)

        created_at = TogglEmbeds._format_discord_datetime(
            project_data.get("created_at") or project_data.get("at")
        )
        if created_at:
            embed.add_field(name="Creation date", value=created_at, inline=False)

        hours_documented = (
            actual_hours if actual_hours is not None else project_data.get("actual_hours")
        )
        embed.add_field(
            name="Hours documented",
            value=str(hours_documented if hours_documented is not None else 0),
            inline=False,
        )
        return embed

    @staticmethod
    def _create_project_data(
        toggl: TogglFunctions,
        project: str,
    ) -> Optional[dict]:
        workspace_id = toggl.workspace_id
        if workspace_id is None:
            raise ValueError("Could not determine your Toggl workspace.")
        project_data = toggl.createProject(workspace_id, name=project)
        if isinstance(project_data, dict) and project_data.get("id") is not None:
            return {
                **project_data,
                "actual_hours": 0,
            }
        return None

    @staticmethod
    def _get_project_data(
        toggl: TogglFunctions,
        project: str,
    ) -> Optional[dict]:
        workspace_id = toggl.workspace_id
        if workspace_id is None:
            raise ValueError("Could not determine your Toggl workspace.")
        project_data = toggl.getProject(project, workspace_id=workspace_id)
        if isinstance(project_data, dict) and project_data.get("id") is not None:
            return project_data
        return None

    @staticmethod
    def project_embed(
        *,
        project: str,
        guild_id: int,
        user_id: int,
        create: bool = False,
    ) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()

        if create:
            project_data = TogglEmbeds._create_project_data(toggl, project)
            if project_data is None:
                embed = discord.Embed(
                    title=":stopwatch: Toggl Project Details",
                    color=discord.Colour.from_str("#552d4f"),
                    description=f"Project {project} already exists",
                )
                embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
                return {"embeds": [embed]}
        else:
            project_data = TogglEmbeds._get_project_data(toggl, project)
            if project_data is None:
                embed = discord.Embed(
                    title=":stopwatch: Toggl Project Details",
                    color=discord.Colour.from_str("#552d4f"),
                    description="No project was found",
                )
                embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
                return {"embeds": [embed]}

        embed = TogglEmbeds._build_project_details_embed(project_data)
        return {"embeds": [embed]}

    """
    WHEN LOOPING OVER RECEIVED PROJECTS
    THE LAST ONE IS NOT FULLY WIRTTEN IN EMBED
    """

    @staticmethod
    def workspaceprojects_embed(guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        workspace_id = toggl.workspace_id
        if workspace_id is None:
            raise ValueError("Could not determine your Toggl workspace.")
        projects = toggl.getProjectsByWorkspace(workspace_id)
        lines = []
        for project in projects:
            project_id = project.get("id")
            project_name = str(project.get("name") or "Unnamed project").strip()
            actual_hours = project.get("actual_hours")
            lines.append(
                f"`{project_id}` | {project_name} | {actual_hours}h"
            )

        embeds = TogglEmbeds._build_line_embeds(
            title=":stopwatch: Toggl All Projects",
            lines=lines,
            empty_description="No projects found.",
        )
        return {"embeds": embeds}

    @staticmethod
    def project_autocomplete_embed(
        current: str,
        guild_id: int,
        user_id: int,
    ) -> list[app_commands.Choice[str]]:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return []

        projects = toggl.findProjectsLike(
            identifier=current,
            workspace_id=toggl.workspace_id,
            limit=25,
        )

        choices: list[app_commands.Choice[str]] = []
        for project in projects:
            project_id = project.get("id")
            if project_id is None:
                continue

            project_name = str(project.get("name") or "").strip() or "Unnamed project"
            label = f"{project_name} | #{project_id}"
            choices.append(
                app_commands.Choice(
                    name=label[:100],
                    value=str(project_id),
                )
            )

        return choices

    #
    # Shortcuts
    #

    @staticmethod
    def createalias_embed(
        guild_id: int,
        user_id: int,
        command: str,
        alias: str,
        arguments: str = "",
        cog_param: object = {},
    ) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        alias_fn = TogglEmbeds._get_function_by_name(command)

        if alias_fn is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl New Shortcut",
                color=discord.Colour.from_str("#552d4f"),
                description="Slash command not found",
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            return {"embeds": [embed]}
        else:
            insert_args = toggl.parseShortcutArguments(arguments)
            cog_param.update(insert_args)

            inserted_data = toggl.saveShortcut2(
                guild_id=guild_id,
                user_id=user_id,
                command=command,
                alias=alias,
                param=cog_param,
            )

            embed = discord.Embed(
                title=":stopwatch: Toggl New Shortcut",
                color=discord.Colour.from_str("#552d4f"),
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            embed.add_field(name="Alias", value=inserted_data["alias"], inline=False)
            embed.add_field(
                name="Command", value=inserted_data["command"], inline=False
            )
            embed.add_field(
                name="Application", value=inserted_data["application"], inline=False
            )
            embed.add_field(name="Id", value=str(inserted_data["_id"]), inline=False)

            for key, value in inserted_data["param"].items():
                embed.add_field(
                    name=f"Param __{str(key)}__", value=str(value), inline=False
                )

            return {"embeds": [embed]}

    """
    - Add number_of_runs increment after each run
        -> creating function inside togglEmbeds might be useful
    - Add argument for passing alias_data as querying will not be needed with AliasCog.py implementation
    """

    @staticmethod
    def usealias_embed(alias: str, guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        alias_data = toggl.findSavedShortcut(alias, guild_id, user_id)
        if alias_data is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl Shortcut",
                color=discord.Colour.from_str("#552d4f"),
                description="Alias not found",
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
            return {"embeds": [embed]}

        fn_embed = TogglEmbeds._get_function_by_name(alias_data["command"])
        params = dict(alias_data.get("param") or {})
        params["guild_id"] = guild_id
        params["user_id"] = user_id
        embed = fn_embed(**params)

        return embed


if __name__ == "__main__":
    embeds = TogglEmbeds()
