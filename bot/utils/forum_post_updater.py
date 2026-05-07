import discord
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

from core.http_client import http_client

PROFICIENCY_EMOJIS = {
    "트라이": "🌱",
    "클경": "👀",
    "반숙": "🔰",
    "숙제": "✅",
    "능동급": "🧠",
}


def _format_proficiency(value):
    value = value or "숙제"
    emoji = PROFICIENCY_EMOJIS.get(value, "✅")
    return f"{emoji} {value}"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(str(value).replace(",", "").strip())
    except Exception:
        return default


def _fmt_num(value: Any, digits: int = 2) -> str:
    return f"{_to_float(value):.{digits}f}"


def _fmt_avg(value: float) -> str:
    return f"{value:.1f}"


def _average(values: List[float]) -> float:
    nums = [v for v in values if v is not None]
    if not nums:
        return 0.0
    return sum(nums) / len(nums)


def _weekday_kr(dt: datetime) -> str:
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return weekdays[dt.weekday()]


def _format_start_date(start_date: Any) -> str:
    if not start_date:
        return ""

    raw = str(start_date).strip()
    if not raw:
        return ""

    candidates = [
        raw,
        raw.replace("Z", "+00:00"),
    ]

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            return f"{dt.strftime('%y.%m.%d')}({_weekday_kr(dt)}) {dt.strftime('%H:%M')}"
        except Exception:
            pass

    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        return f"{dt.strftime('%y.%m.%d')}({_weekday_kr(dt)}) {dt.strftime('%H:%M')}"
    except Exception:
        return raw


def _format_member_line(member: Dict[str, Any], role_emoji: str) -> str:
    user_id = member.get("user_id")
    mention = f"<@{user_id}>" if user_id else "알 수 없음"

    char_name = member.get("char_name", "이름없음")
    class_name = member.get("class_name", "직업정보없음")
    item_lvl = _fmt_num(member.get("item_lvl"), 2)
    combat_power = _fmt_num(member.get("combat_power"), 2)

    proficiency = _format_proficiency(member.get("proficiency"))

    return (
        f"{mention} {role_emoji} **{char_name}** · **{proficiency}**\n"
        f"Lv.{item_lvl} | {class_name} | 전투력 {combat_power}"
    )


def build_party_header_content(party: Dict[str, Any], participants: Dict[str, List[Dict[str, Any]]]) -> str:
    dealers = participants.get("dealers", []) or []
    supporters = participants.get("supporters", []) or []

    owner = party.get("owner")
    owner_mention = f"<@{owner}>" if owner else ""

    return f"🟢 딜러 **{len(dealers)}명** · 서포터 **{len(supporters)}명** {owner_mention}".strip()


def build_party_embed(party: Dict[str, Any], participants: Dict[str, List[Dict[str, Any]]]) -> discord.Embed:
    raid_name = party.get("custom_raid_name") or party.get("raid_name", "-")
    difficulty = party.get("custom_difficulty") or party.get("difficulty", "-")
    owner = party.get("owner")
    owner_mention = f"<@{owner}>" if owner else "알 수 없음"

    dealers = participants.get("dealers", []) or []
    supporters = participants.get("supporters", []) or []
    all_members = dealers + supporters

    start_text = _format_start_date(party.get("start_date"))
    embed_title = f"[{raid_name} : {difficulty}]"
    if start_text:
        embed_title += f" {start_text}"

    dealer_lines = [_format_member_line(member, "⚔️") for member in dealers]
    supporter_lines = [_format_member_line(member, "🛡️") for member in supporters]

    avg_item_lvl = _average([_to_float(m.get("item_lvl")) for m in all_members])
    avg_combat = _average([_to_float(m.get("combat_power")) for m in all_members])

    embed = discord.Embed(
        title=embed_title,
        description=f"공격대 생성자 : {owner_mention}",
        color=discord.Color.from_rgb(88, 101, 242),
    )

    embed.add_field(
        name=f"딜러 ({len(dealers)}명)",
        value="\n\n".join(dealer_lines) if dealer_lines else "== 없음 ==",
        inline=False,
    )

    embed.add_field(
        name=f"서포터 ({len(supporters)}명)",
        value="\n\n".join(supporter_lines) if supporter_lines else "== 없음 ==",
        inline=False,
    )

    embed.add_field(
        name="공격대 평균 정보",
        value=(
            f"평균 레벨 : **{_fmt_avg(avg_item_lvl)}**\n"
            f"평균 전투력 : **{_fmt_avg(avg_combat)}**"
        ),
        inline=False,
    )

    return embed


async def fetch_party_detail(party_id: int) -> Optional[Dict[str, Any]]:
    try:
        resp = await http_client.get(f"/party/{party_id}")
        if resp.status_code != 200:
            return None
        return resp.json() or {}
    except Exception:
        return None


async def update_forum_post(bot: discord.Bot, party_id: int) -> Tuple[bool, str]:
    data = await fetch_party_detail(party_id)
    if not data:
        return False, "파티 상세 정보를 불러오지 못했습니다."

    party = data.get("party", {}) or {}
    participants = data.get("participants", {}) or {}

    thread_manage_id = party.get("thread_manage_id")
    if not thread_manage_id:
        return False, "thread_manage_id가 없습니다."

    thread = bot.get_channel(int(thread_manage_id))
    if thread is None:
        try:
            thread = await bot.fetch_channel(int(thread_manage_id))
        except Exception:
            thread = None

    if thread is None:
        return False, "포럼 스레드를 찾지 못했습니다."

    content = build_party_header_content(party, participants)
    embed = build_party_embed(party, participants)

    try:
        first_message = None
        async for msg in thread.history(limit=20, oldest_first=True):
            if msg.author.id == bot.user.id:
                first_message = msg
                break

        if first_message is None:
            return False, "수정할 봇 메시지를 찾지 못했습니다."

        await first_message.edit(content=content, embed=embed)
        return True, "포럼 포스트를 갱신했습니다."
    except Exception as e:
        return False, f"포럼 포스트 갱신 실패: {e}"