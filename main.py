#!/usr/bin/env python3

import asyncio
import websockets
from websockets.server import serve
from game_manager import GameManager
from member import Member
from utils import send_object, recv_object

games = dict()


async def handleRoomCreation(ws, initObj, setRoom):
    if "name" in initObj and initObj["name"].strip() != "":
        gm = GameManager(initObj["packs"], initObj["questions"], initObj["answers"])

        while gm.joinCode in games:
            gm.regenJoinCode()

        m = Member(ws, initObj["name"])
        gm.addMember(m)
        games[gm.joinCode] = gm
        setRoom(gm.joinCode)
        await send_object(
            ws,
            {"action": "roomMade", "joinCode": gm.joinCode, "setName": initObj["name"]},
        )
        nextObj = await recv_object(ws)

        if "action" in nextObj:
            if nextObj["action"] == "startGame":
                await asyncio.wait(
                    [games[gm.joinCode].startGame(), m.runGameLoop()],
                    return_when=asyncio.FIRST_COMPLETED,
                )
    else:
        await send_object(
            ws, {"action": "error", "content": "Please make sure to set a name."}
        )


async def handleRoomJoin(ws, initObj, setRoom):
    if "name" in initObj and initObj["name"].strip() != "":
        if "joinCode" in initObj and len(initObj["joinCode"]) == 6:
            if (
                initObj["joinCode"] in games
                and games[initObj["joinCode"]].status == "open"
            ):
                for member in games[initObj["joinCode"]].members:
                    await send_object(
                        member.ws, {"action": "memberJoined", "name": initObj["name"]}
                    )
                await send_object(
                    ws,
                    {
                        "action": "roomJoined",
                        "members": [m.name for m in games[initObj["joinCode"]].members],
                        "setName": initObj["name"],
                        "joinCode": initObj["joinCode"],
                    },
                )
                setRoom(initObj["joinCode"])

                m = Member(ws, initObj["name"])
                games[initObj["joinCode"]].addMember(m)
                await m.runGameLoop()
            else:
                await send_object(
                    ws, {"action": "error", "content": "This room does not exist."}
                )
        else:
            await send_object(
                ws,
                {
                    "action": "error",
                    "content": "Please make sure to specify a valid room code.",
                },
            )
    else:
        await send_object(
            ws, {"action": "error", "content": "Please make sure to set a name."}
        )


async def handler(ws):
    while True:
        print("replies")

        currentRoom = ""

        def setRoom(joinCode):
            nonlocal currentRoom
            currentRoom = joinCode

        try:
            while True:
                initObj = await recv_object(ws)
                if "action" in initObj:
                    if initObj["action"] == "makeRoom":
                        await handleRoomCreation(ws, initObj, setRoom)
                    elif initObj["action"] == "joinRoom":
                        await handleRoomJoin(ws, initObj, setRoom)
                    else:
                        await send_object(
                            ws, {"action": "error", "content": "Invalid action."}
                        )
        except websockets.ConnectionClosed as e:
            if currentRoom != "":
                if games[currentRoom].members[0].ws == ws:
                    games[currentRoom].members.pop(0)
                    await games[currentRoom].broadcastToAll({"action": "hostLeft"})
                else:
                    index = 0
                    for member in games[currentRoom].members:
                        if member.ws == ws:
                            break
                        index += 1
                    await games[currentRoom].broadcastToAll(
                        {
                            "action": "memberLeft",
                            "name": games[currentRoom].members.pop(index).name,
                        }
                    )
            else:
                print("Whoops")

        finally:
            pass


async def main():
    async with websockets.serve(handler, "", 8765):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
