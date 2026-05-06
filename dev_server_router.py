from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from database.connection import get_db

router = APIRouter()


class ForumChannelSetRequest(BaseModel):
    guild_id: str = Field(..., example="123456789012345678")
    forum_channel_id: str = Field(..., example="123456789012345678")


@router.post("/forum-channel")
async def set_forum_channel(body: ForumChannelSetRequest):
    async with get_db() as db:
        existing = await db.execute(
            "SELECT id FROM server WHERE guild_id = ? LIMIT 1",
            (body.guild_id,),
        ) or []

        if existing:
            await db.execute(
                "UPDATE server SET forum_channel_id = ? WHERE guild_id = ?",
                (body.forum_channel_id, body.guild_id),
            )
        else:
            await db.execute(
                """
                INSERT INTO server (guild_id, forum_channel_id)
                VALUES (?, ?)
                """,
                (body.guild_id, body.forum_channel_id),
            )

        await db.commit()

    return {
        "ok": True,
        "guild_id": body.guild_id,
        "forum_channel_id": body.forum_channel_id,
    }


@router.get("/forum-channel/{guild_id}")
async def get_forum_channel(guild_id: str):
    async with get_db() as db:
        rows = await db.execute(
            "SELECT guild_id, forum_channel_id FROM server WHERE guild_id = ? LIMIT 1",
            (guild_id,),
        ) or []

        if not rows:
            raise HTTPException(status_code=404, detail="Server config not found")

        return rows[0]