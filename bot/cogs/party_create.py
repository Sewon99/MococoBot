import discord
from discord.ext import commands

from core.http_client import http_client


RAID_NAMES = [
    "서막: 에키드나",
    "1막: 에기르",
    "2막: 아브렐슈드",
    "3막: 모르둠",
    "4막: 아르모체",
    "종막: 카제로스",
    "그림자 레이드: 세르카",
    "지평의 성당",
]

DIFFICULTIES = [
    "노말",
    "하드",
    "나이트메어",
    "1단계",
    "2단계",
    "3단계",
]


class PartyEntryView(discord.ui.View):
    def __init__(self, party_id: int):
        super().__init__(timeout=None)

        join_button = discord.ui.Button(
            label="파티 참가",
            style=discord.ButtonStyle.success,
            custom_id=f"party_join_{party_id}",
            emoji="⚔️",
        )
        join_button.callback = self._noop_callback
        self.add_item(join_button)

    async def _noop_callback(self, interaction: discord.Interaction):
        pass


class PartyCreate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _find_raid_id(self, raid_name: str, difficulty: str):
        try:
            resp = await http_client.get("/debug/raid-list")
            if resp.status_code != 200:
                return None, "레이드 목록을 불러오지 못했습니다."

            payload = resp.json() or {}
            raids = payload.get("data", [])

            for raid in raids:
                if (
                    str(raid.get("name", "")).strip() == raid_name.strip()
                    and str(raid.get("difficulty", "")).strip() == difficulty.strip()
                ):
                    return raid.get("id"), None

            return None, f"'{raid_name} / {difficulty}' 레이드를 찾지 못했습니다."
        except Exception as e:
            return None, f"레이드 조회 중 오류: {e}"

    @discord.slash_command(name="파티생성", description="레이드 모집 파티를 생성합니다.")
    async def create_party(
        self,
        ctx: discord.ApplicationContext,
        제목: str,
        레이드명: str,
        난이도: str,
        안내문: str = "편하게 신청해주세요.",
    ):
        await ctx.defer(ephemeral=True)

        try:
            raid_id, error = await self._find_raid_id(레이드명, 난이도)
            if error:
                await ctx.followup.send(f"❌ {error}", ephemeral=True)
                return

            create_resp = await http_client.post(
                "/party/create",
                json={
                    "title": 제목,
                    "guild_id": int(ctx.guild.id) if ctx.guild else None,
                    "raid_id": int(raid_id),
                    "start_date": None,
                    "owner": int(ctx.user.id),
                    "message": 안내문,
                    "party_slots": 1,
                },
            )

            try:
                create_data = create_resp.json() or {}
            except Exception:
                create_data = {}

            if create_resp.status_code != 200:
                detail = create_data.get("detail") or create_data.get("message") or f"상태 코드: {create_resp.status_code}"
                await ctx.followup.send(f"❌ 파티 생성 실패: {detail}", ephemeral=True)
                return

            party_id = int(create_data["party_id"])

            detail_resp = await http_client.get(f"/party/{party_id}")
            if detail_resp.status_code != 200:
                await ctx.followup.send("❌ 파티는 생성됐지만 상세 정보를 불러오지 못했습니다.", ephemeral=True)
                return

            detail_data = detail_resp.json() or {}
            party = detail_data.get("party", {})

            dealer_count = party.get("dealer_count", 0)
            supporter_count = party.get("supporter_count", 0)
            total_count = party.get("total_count", 0)
            recommended_dealer = party.get("recommended_dealer", party.get("dealer", "-"))
            recommended_supporter = party.get("recommended_supporter", party.get("supporter", "-"))
            min_lvl = party.get("min_lvl", "-")

            embed = discord.Embed(
                title=f"📌 {제목}",
                description=안내문,
                color=discord.Color.blurple(),
            )
            embed.add_field(name="레이드", value=f"{레이드명} / {난이도}", inline=True)
            embed.add_field(name="최소 레벨", value=str(min_lvl), inline=True)
            embed.add_field(name="파티 ID", value=str(party_id), inline=True)

            embed.add_field(
                name="현재 모집 인원",
                value=f"딜러 **{dealer_count}명** / 서폿 **{supporter_count}명** / 총 **{total_count}명**",
                inline=False,
            )
            embed.add_field(
                name="기본 구성 참고",
                value=f"딜러 **{recommended_dealer}명** / 서폿 **{recommended_supporter}명**",
                inline=False,
            )

            view = PartyEntryView(party_id)
            await ctx.channel.send(embed=embed, view=view)
            await ctx.followup.send(f"✅ 파티를 생성했어요. (party_id={party_id})", ephemeral=True)

        except Exception as e:
            await ctx.followup.send(f"❌ 오류가 발생했습니다: {e}", ephemeral=True)


def setup(bot):
    bot.add_cog(PartyCreate(bot))