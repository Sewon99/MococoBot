import discord
from discord.ext import commands

from core.http_client import http_client


class ForumConfig(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(name="포럼채널설정", description="모집 포스트를 생성할 포럼 채널을 등록합니다.")
    async def set_forum_channel(
        self,
        ctx: discord.ApplicationContext,
        채널: discord.Option(discord.ForumChannel, "포럼 채널", required=True),
    ):
        await ctx.defer(ephemeral=True)

        try:
            resp = await http_client.post(
                "/server/forum-channel",
                json={
                    "guild_id": str(ctx.guild.id),
                    "forum_channel_id": str(채널.id),
                },
            )

            if resp.status_code != 200:
                try:
                    data = resp.json() or {}
                except Exception:
                    data = {}
                detail = data.get("detail") or data.get("message") or f"상태 코드: {resp.status_code}"
                await ctx.followup.send(f"❌ 설정 실패: {detail}", ephemeral=True)
                return

            await ctx.followup.send(
                f"✅ 모집 포스트용 포럼 채널을 {채널.mention} 으로 설정했어요.",
                ephemeral=True,
            )

        except Exception as e:
            await ctx.followup.send(f"❌ 오류가 발생했습니다: {e}", ephemeral=True)


def setup(bot):
    bot.add_cog(ForumConfig(bot))