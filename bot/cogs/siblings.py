import discord
from discord.ext import commands
from discord import option
from commands.siblings import ExpeditionRegisterChannelModal
from handler.siblings import handle_expedition_register_button

class SiblingsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(name="원정대", description="원정대 등록 및 관리 기능입니다.")
    async def expedition_manage(self, ctx: discord.ApplicationContext):
        try:
            await handle_expedition_register_button(ctx.interaction)
        except Exception as e:
            print(f"오류: {e}")


def setup(bot):
    bot.add_cog(SiblingsCog(bot))