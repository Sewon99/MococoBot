import discord
import contextlib
from discord.ext import commands
from datetime import datetime, timedelta

from core.http_client import http_client
from utils.forum_post_updater import build_party_embed, build_party_header_content


def get_date_options():
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    today = datetime.now()
    options = []

    for i in range(14):
        d = today + timedelta(days=i)
        label = f"{d.strftime('%Y-%m-%d')} ({weekdays[d.weekday()]})"
        value = d.strftime("%Y-%m-%d")
        options.append(discord.SelectOption(label=label, value=value))

    return options


def normalize_time_string(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None

    try:
        parts = raw.split(":")
        if len(parts) != 2:
            return None

        hour = int(parts[0])
        minute = int(parts[1])

        if hour < 0 or hour > 23:
            return None
        if minute < 0 or minute > 59:
            return None

        return f"{hour:02d}:{minute:02d}"
    except Exception:
        return None


class PartyEntryView(discord.ui.View):
    def __init__(self, party_id: int):
        super().__init__(timeout=None)

        join_button = discord.ui.Button(
            label="파티 참가",
            style=discord.ButtonStyle.success,
            custom_id=f"party_join_{party_id}",
            emoji="⚔️",
        )
        leave_button = discord.ui.Button(
            label="파티 탈퇴",
            style=discord.ButtonStyle.danger,
            custom_id=f"party_leave_{party_id}",
            emoji="🚪",
        )

        join_button.callback = self._noop_callback
        leave_button.callback = self._noop_callback

        self.add_item(join_button)
        self.add_item(leave_button)

    async def _noop_callback(self, interaction: discord.Interaction):
        pass


class PartyCreateModal(discord.ui.Modal):
    def __init__(self, parent_view: "PartyCreateForumView"):
        super().__init__(title="파티 모집 정보 입력")
        self.parent_view = parent_view

        self.title_input = discord.ui.InputText(
            label="제목",
            placeholder="예: 세르카 나이트메어 모집",
            required=True,
            max_length=100,
            value=parent_view.party_title or "",
        )

        self.raid_input = discord.ui.InputText(
            label="레이드 / 콘텐츠명",
            placeholder="예: 그림자 레이드 : 세르카",
            required=True,
            max_length=100,
            value=parent_view.raid_name or "",
        )

        self.difficulty_input = discord.ui.InputText(
            label="난이도 / 구분",
            placeholder="예: 나이트메어, 하드, 2단계, 트라이 등",
            required=True,
            max_length=100,
            value=parent_view.difficulty or "",
        )

        self.time_input = discord.ui.InputText(
            label="시간 (HH:MM)",
            placeholder="예: 21:30",
            required=True,
            max_length=5,
            value=parent_view.time_value or "",
        )

        self.message_input = discord.ui.InputText(
            label="안내문",
            placeholder="예: 편하게 신청해주세요.",
            required=False,
            style=discord.InputTextStyle.long,
            max_length=300,
            value=parent_view.party_message or "",
        )

        self.add_item(self.title_input)
        self.add_item(self.raid_input)
        self.add_item(self.difficulty_input)
        self.add_item(self.time_input)
        self.add_item(self.message_input)

    async def callback(self, interaction: discord.Interaction):
        normalized_time = normalize_time_string(self.time_input.value)
        if not normalized_time:
            await interaction.response.send_message(
                "❌ 시간 형식이 올바르지 않습니다. `21:30` 형식으로 입력해주세요.",
                ephemeral=True,
            )
            return

        title = self.title_input.value.strip()
        raid_name = self.raid_input.value.strip()
        difficulty = self.difficulty_input.value.strip()

        if not title or not raid_name or not difficulty:
            await interaction.response.send_message(
                "❌ 제목, 레이드명, 난이도는 비워둘 수 없습니다.",
                ephemeral=True,
            )
            return

        self.parent_view.party_title = title
        self.parent_view.raid_name = raid_name
        self.parent_view.difficulty = difficulty
        self.parent_view.time_value = normalized_time
        self.parent_view.party_message = (self.message_input.value or "").strip() or "편하게 신청해주세요."

        embed = self.parent_view.build_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class DateSelect(discord.ui.Select):
    def __init__(self, parent_view: "PartyCreateForumView"):
        super().__init__(
            placeholder="날짜를 선택하세요",
            min_values=1,
            max_values=1,
            options=get_date_options(),
            row=0,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.date_value = self.values[0]
        embed = self.parent_view.build_preview_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class PartyCreateForumView(discord.ui.View):
    def __init__(self, cog: "PartyCreateForum", guild: discord.Guild, user: discord.User):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user

        self.raid_name = None
        self.difficulty = None
        self.date_value = None
        self.time_value = None
        self.party_title = None
        self.party_message = "편하게 신청해주세요."

        self.refresh_items()

    def refresh_items(self):
        self.clear_items()

        self.add_item(DateSelect(self))

        edit_button = discord.ui.Button(
            label="모집 정보 입력",
            style=discord.ButtonStyle.secondary,
            emoji="✏️",
            row=1,
        )
        create_button = discord.ui.Button(
            label="파티 생성",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=2,
        )
        cancel_button = discord.ui.Button(
            label="취소",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            row=2,
        )

        async def edit_callback(interaction: discord.Interaction):
            modal = PartyCreateModal(self)
            await interaction.response.send_modal(modal)

        async def create_callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

            if not all([
                self.raid_name,
                self.difficulty,
                self.date_value,
                self.time_value,
                self.party_title,
            ]):
                await interaction.followup.send(
                    "❌ 날짜, 제목, 레이드명, 난이도, 시간을 모두 입력해주세요.",
                    ephemeral=True,
                )
                return

            ok, msg = await self.cog.create_party_forum_from_view(
                interaction=interaction,
                guild=self.guild,
                user=self.user,
                title=self.party_title,
                raid_name=self.raid_name,
                difficulty=self.difficulty,
                date_value=self.date_value,
                time_value=self.time_value,
                message=self.party_message,
            )

            if ok:
                for item in self.children:
                    item.disabled = True
                with contextlib.suppress(Exception):
                    await interaction.edit_original_response(view=self)

        async def cancel_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(
                content="파티 생성이 취소되었습니다.",
                embed=None,
                view=None,
            )

        edit_button.callback = edit_callback
        create_button.callback = create_callback
        cancel_button.callback = cancel_callback

        self.add_item(edit_button)
        self.add_item(create_button)
        self.add_item(cancel_button)

    def build_preview_embed(self):
        def done_text(value: str | None, empty_text: str = "미입력"):
            return f"✅ {value}" if value else f"❌ {empty_text}"

        embed = discord.Embed(
            title="⚒️ 파티 모집 생성",
            description="날짜를 선택하고, 모집 정보를 직접 입력한 뒤 **파티 생성** 버튼을 눌러주세요.",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="🗓️ 일정",
            value=(
                f"**날짜**: {done_text(self.date_value, '미선택')}\n"
                f"**시간**: {done_text(self.time_value)}"
            ),
            inline=False,
        )

        embed.add_field(
            name="📌 모집 정보",
            value=(
                f"**제목**: {done_text(self.party_title)}\n"
                f"**레이드**: {done_text(self.raid_name)}\n"
                f"**난이도/구분**: {done_text(self.difficulty)}"
            ),
            inline=False,
        )

        embed.add_field(
            name="📝 안내문",
            value=self.party_message or "편하게 신청해주세요.",
            inline=False,
        )

        missing = []
        if not self.date_value:
            missing.append("날짜")
        if not self.time_value:
            missing.append("시간")
        if not self.party_title:
            missing.append("제목")
        if not self.raid_name:
            missing.append("레이드명")
        if not self.difficulty:
            missing.append("난이도/구분")

        if missing:
            embed.add_field(
                name="⚠️ 아직 필요한 입력",
                value=", ".join(missing),
                inline=False,
            )
            embed.set_footer(text="날짜 선택 후, 모집 정보 입력 버튼에서 제목/레이드/난이도/시간을 입력하세요.")
        else:
            embed.add_field(
                name="✅ 생성 준비 완료",
                value="이제 **파티 생성** 버튼을 눌러 모집글을 만들 수 있어요.",
                inline=False,
            )
            embed.set_footer(text="모든 정보가 입력되었습니다.")

        return embed


class PartyCreateForum(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def create_party_forum_from_view(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        user: discord.User,
        title: str,
        raid_name: str,
        difficulty: str,
        date_value: str,
        time_value: str,
        message: str,
    ):
        try:
            forum_resp = await http_client.get(f"/server/forum-channel/{guild.id}")
            if forum_resp.status_code != 200:
                await interaction.followup.send(
                    "❌ 먼저 `/포럼채널설정` 으로 포럼 채널을 등록해주세요.",
                    ephemeral=True,
                )
                return False, "forum channel not set"

            forum_data = forum_resp.json() or {}
            forum_channel_id = forum_data.get("forum_channel_id")
            if not forum_channel_id:
                await interaction.followup.send("❌ 포럼 채널이 설정되어 있지 않습니다.", ephemeral=True)
                return False, "forum channel empty"

            forum_channel = guild.get_channel(int(forum_channel_id))
            if forum_channel is None:
                try:
                    forum_channel = await guild.fetch_channel(int(forum_channel_id))
                except Exception:
                    forum_channel = None

            if forum_channel is None or not isinstance(forum_channel, discord.ForumChannel):
                await interaction.followup.send(
                    "❌ 설정된 채널을 찾을 수 없거나 포럼 채널이 아닙니다.",
                    ephemeral=True,
                )
                return False, "forum channel invalid"

            start_date = f"{date_value} {time_value}:00"

            create_resp = await http_client.post(
                "/party/create",
                json={
                    "title": title,
                    "guild_id": int(guild.id),
                    "custom_raid_name": raid_name,
                    "custom_difficulty": difficulty,
                    "start_date": start_date,
                    "owner": int(user.id),
                    "message": message,
                    "party_slots": 1,
                },
            )

            try:
                create_data = create_resp.json() or {}
            except Exception:
                create_data = {}

            if create_resp.status_code != 200:
                detail = create_data.get("detail") or create_data.get("message") or f"상태 코드: {create_resp.status_code}"
                await interaction.followup.send(f"❌ 파티 생성 실패: {detail}", ephemeral=True)
                return False, detail

            party_id = int(create_data["party_id"])

            detail_resp = await http_client.get(f"/party/{party_id}")
            if detail_resp.status_code != 200:
                await interaction.followup.send(
                    "❌ 파티는 생성됐지만 상세 정보를 불러오지 못했습니다.",
                    ephemeral=True,
                )
                return False, "detail fetch fail"

            detail_data = detail_resp.json() or {}
            party = detail_data.get("party", {})

            participants = {"dealers": [], "supporters": []}
            content = build_party_header_content(party, participants)
            embed = build_party_embed(party, participants)

            view = PartyEntryView(party_id)

            thread = await forum_channel.create_thread(
                name=title[:100],
                content=content,
                embed=embed,
                view=view,
                auto_archive_duration=1440,
            )

            created_thread = thread.thread if hasattr(thread, "thread") else thread
            thread_id = getattr(created_thread, "id", None)

            if thread_id:
                await http_client.patch(
                    f"/party/{party_id}/thread",
                    json={
                        "thread_manage_id": str(thread_id),
                        "guild_id": str(guild.id),
                    },
                )

            await interaction.followup.send(
                f"✅ 포럼 채널에 모집 포스트를 생성했어요. (party_id={party_id})",
                ephemeral=True,
            )
            return True, "ok"

        except Exception as e:
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {e}", ephemeral=True)
            return False, str(e)

    @discord.slash_command(name="파티생성포럼", description="수기 입력으로 포럼 채널 모집 포스트를 생성합니다.")
    async def create_party_forum(self, ctx: discord.ApplicationContext):
        if not ctx.guild:
            await ctx.respond("❌ 서버에서만 사용할 수 있습니다.", ephemeral=True)
            return

        view = PartyCreateForumView(self, ctx.guild, ctx.user)
        embed = view.build_preview_embed()
        await ctx.respond(embed=embed, view=view, ephemeral=True)


def setup(bot):
    bot.add_cog(PartyCreateForum(bot))