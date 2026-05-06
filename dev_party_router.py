from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from fastapi import Body

from database.connection import get_db


router = APIRouter()


class PartyCreateRequest(BaseModel):
    title: str = Field(..., example="세르카 모집")
    guild_id: Optional[int] = Field(None, example=123456789012345678)
    raid_id: Optional[int] = Field(None, example=1)
    custom_raid_name: Optional[str] = Field(None, example="그림자 레이드 : 세르카")
    custom_difficulty: Optional[str] = Field(None, example="나이트메어")
    start_date: Optional[str] = Field(None, example="2026-04-20 20:00:00")
    owner: Optional[int] = Field(None, example=418036455210876928)
    message: Optional[str] = Field(None, example="편하게 와주세요")
    party_slots: int = Field(1, ge=1, le=8, example=1)


class PartyJoinRequest(BaseModel):
    character_id: int
    user_id: int
    role: int  # 0=dealer, 1=supporter


async def get_or_create_free_raid_id(db) -> int:
    rows = await db.execute(
        """
        SELECT id
        FROM raid
        WHERE name = ? AND difficulty = ?
        LIMIT 1
        """,
        ("자유입력", "자유입력"),
    ) or []

    if rows:
        return int(rows[0]["id"])

    await db.execute(
        """
        INSERT INTO raid (name, difficulty, min_lvl, dealer, supporter)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("자유입력", "자유입력", 0, 0, 0),
    )
    await db.commit()

    return int(db.lastrowid)


@router.get("/list")
async def list_parties():
    async with get_db() as db:
        rows = await db.execute(
            """
            SELECT
                p.id,
                p.title,
                p.guild_id,
                p.raid_id,
                p.start_date,
                p.owner,
                p.message,
                p.custom_raid_name,
                p.custom_difficulty,
                p.thread_manage_id,
                p.is_active,
                p.is_dealer_closed,
                p.is_supporter_closed,
                p.party_slots,
                r.name AS raid_name,
                r.difficulty,
                r.min_lvl,
                r.dealer,
                r.supporter
            FROM party p
            JOIN raid r ON p.raid_id = r.id
            ORDER BY p.id DESC
            """
        ) or []

        for row in rows:
            count_rows = await db.execute(
                """
                SELECT
                    SUM(CASE WHEN role = 0 THEN 1 ELSE 0 END) AS dealer_count,
                    SUM(CASE WHEN role = 1 THEN 1 ELSE 0 END) AS supporter_count,
                    COUNT(*) AS total_count
                FROM participants
                WHERE party_id = ?
                """,
                (row["id"],),
            ) or []

            counts = count_rows[0] if count_rows else {}
            row["dealer_count"] = int(counts.get("dealer_count") or 0)
            row["supporter_count"] = int(counts.get("supporter_count") or 0)
            row["total_count"] = int(counts.get("total_count") or 0)

            # 참고용 값
            row["recommended_dealer"] = int(row["dealer"])
            row["recommended_supporter"] = int(row["supporter"])

        return {"data": rows}


@router.get("/{party_id}")
async def get_party(party_id: int):
    async with get_db() as db:
        party_rows = await db.execute(
            """
            SELECT
                p.id,
                p.title,
                p.guild_id,
                p.raid_id,
                p.start_date,
                p.owner,
                p.message,
                p.custom_raid_name,
                p.custom_difficulty,
                p.thread_manage_id,
                p.is_active,
                p.is_dealer_closed,
                p.is_supporter_closed,
                p.party_slots,
                r.name AS raid_name,
                r.difficulty,
                r.min_lvl,
                r.dealer,
                r.supporter
            FROM party p
            JOIN raid r ON p.raid_id = r.id
            WHERE p.id = ?
            """,
            (party_id,),
        ) or []

        if not party_rows:
            raise HTTPException(status_code=404, detail="Party not found")

        party = party_rows[0]

        participant_rows = await db.execute(
            """
            SELECT
                pt.id,
                pt.party_id,
                pt.character_id,
                pt.user_id,
                pt.role,
                pt.joined_at,
                c.char_name,
                c.item_lvl,
                c.combat_power,
                cl.name AS class_name,
                cl.emoji AS class_emoji
            FROM participants pt
            JOIN `character` c ON pt.character_id = c.id
            LEFT JOIN class cl ON c.class_id = cl.id
            WHERE pt.party_id = ?
            ORDER BY pt.joined_at ASC
            """,
            (party_id,),
        ) or []

        dealers = []
        supporters = []
        party["dealer_count"] = len(dealers)
        party["supporter_count"] = len(supporters)
        party["total_count"] = len(dealers) + len(supporters)
        party["recommended_dealer"] = int(party["dealer"])
        party["recommended_supporter"] = int(party["supporter"])

        for row in participant_rows:
            item = dict(row)
            if int(item["role"]) == 0:
                dealers.append(item)
            else:
                supporters.append(item)

        return {
            "party": party,
            "participants": {
                "dealers": dealers,
                "supporters": supporters,
            },
        }


@router.post("/create")
async def create_party(body: PartyCreateRequest):
    async with get_db() as db:
        raid_id = body.raid_id

        if raid_id is not None:
            raid_rows = await db.execute(
                "SELECT id FROM raid WHERE id = ?",
                (raid_id,),
            ) or []

            if not raid_rows:
                raise HTTPException(status_code=404, detail="Raid not found")
        else:
            raid_id = await get_or_create_free_raid_id(db)

        await db.execute(
            """
            INSERT INTO party (
                title,
                guild_id,
                raid_id,
                custom_raid_name,
                custom_difficulty,
                start_date,
                owner,
                message,
                party_slots
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                body.title,
                body.guild_id,
                raid_id,
                body.custom_raid_name,
                body.custom_difficulty,
                body.start_date,
                body.owner,
                body.message,
                body.party_slots,
            ),
        )
        party_id = db.lastrowid
        await db.commit()

        return {
            "ok": True,
            "party_id": party_id,
            "message": "Party created successfully",
        }


@router.post("/{party_id}/join")
async def join_party(party_id: int, body: PartyJoinRequest):
    if body.role not in (0, 1):
        raise HTTPException(status_code=400, detail="role must be 0 or 1")

    async with get_db() as db:
        party_rows = await db.execute(
            """
            SELECT
                p.id,
                p.is_active,
                p.is_dealer_closed,
                p.is_supporter_closed,
                p.party_slots,
                r.min_lvl,
                r.dealer,
                r.supporter
            FROM party p
            JOIN raid r ON p.raid_id = r.id
            WHERE p.id = ?
            """,
            (party_id,),
        ) or []

        if not party_rows:
            raise HTTPException(status_code=404, detail="Party not found")

        party = party_rows[0]

        if int(party["is_active"]) != 1:
            raise HTTPException(status_code=400, detail="Party is not active")

        if body.role == 0 and int(party["is_dealer_closed"]) == 1:
            raise HTTPException(status_code=400, detail="Dealer recruitment is closed")

        if body.role == 1 and int(party["is_supporter_closed"]) == 1:
            raise HTTPException(status_code=400, detail="Supporter recruitment is closed")

        char_rows = await db.execute(
            """
            SELECT c.id, c.item_lvl
            FROM `character` c
            WHERE c.id = ?
            """,
            (body.character_id,),
        ) or []

        if not char_rows:
            raise HTTPException(status_code=404, detail="Character not found")

        char = char_rows[0]
        if float(char["item_lvl"]) < float(party["min_lvl"]):
            raise HTTPException(status_code=400, detail="Item level is too low")

        # 같은 유저가 같은 파티에 중복 참가하는 것만 막음
        dup_rows = await db.execute(
            """
            SELECT id
            FROM participants
            WHERE party_id = ? AND user_id = ?
            """,
            (party_id, body.user_id),
        ) or []

        if dup_rows:
            raise HTTPException(status_code=409, detail="User already joined this party")

        await db.execute(
            """
            INSERT INTO participants (party_id, character_id, user_id, role)
            VALUES (?, ?, ?, ?)
            """,
            (party_id, body.character_id, body.user_id, body.role),
        )
        await db.commit()

        # 현재 인원 집계
        count_rows = await db.execute(
            """
            SELECT
                SUM(CASE WHEN role = 0 THEN 1 ELSE 0 END) AS dealer_count,
                SUM(CASE WHEN role = 1 THEN 1 ELSE 0 END) AS supporter_count,
                COUNT(*) AS total_count
            FROM participants
            WHERE party_id = ?
            """,
            (party_id,),
        ) or []

        counts = count_rows[0] if count_rows else {}
        dealer_count = int(counts.get("dealer_count") or 0)
        supporter_count = int(counts.get("supporter_count") or 0)
        total_count = int(counts.get("total_count") or 0)

        return {
            "ok": True,
            "message": "Joined party successfully",
            "party_id": party_id,
            "character_id": body.character_id,
            "role": body.role,
            "dealer_count": dealer_count,
            "supporter_count": supporter_count,
            "total_count": total_count,
        }
    
@router.patch("/{party_id}/thread")
async def set_party_thread(party_id: int, body: dict = Body(...)):
    thread_id = body.get("thread_manage_id")
    guild_id = body.get("guild_id")

    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_manage_id is required")

    async with get_db() as db:
        rows = await db.execute(
            "SELECT id FROM party WHERE id = ? LIMIT 1",
            (party_id,),
        ) or []

        if not rows:
            raise HTTPException(status_code=404, detail="Party not found")

        await db.execute(
            """
            UPDATE party
            SET thread_manage_id = ?, guild_id = COALESCE(?, guild_id)
            WHERE id = ?
            """,
            (str(thread_id), str(guild_id) if guild_id else None, party_id),
        )
        await db.commit()

    return {
        "ok": True,
        "party_id": party_id,
        "thread_manage_id": str(thread_id),
    }

@router.delete("/{party_id}/participants/{user_id}")
async def leave_party(party_id: int, user_id: str):
    async with get_db() as db:
        rows = await db.execute(
            """
            SELECT id
            FROM participants
            WHERE party_id = ? AND user_id = ?
            LIMIT 1
            """,
            (party_id, str(user_id)),
        ) or []

        if not rows:
            raise HTTPException(status_code=404, detail="Participant not found")

        participant_id = rows[0]["id"]

        await db.execute(
            "DELETE FROM participants WHERE id = ?",
            (participant_id,),
        )
        await db.commit()

        return {
            "ok": True,
            "message": "Left party successfully",
            "party_id": party_id,
            "user_id": str(user_id),
        }