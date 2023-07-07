#!/usr/bin/env python3

import asyncio
import mimetypes
import websockets
from websockets.server import serve
from game_manager import GameManager
from member import Member
from utils import send_object, recv_object
import os
import asyncio
import websockets
from http import HTTPStatus

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
                pass

        finally:
            pass


async def process_request(path, request_headers):
    """Serves a file when doing a GET request with a valid path."""

    if "Upgrade" in request_headers:
        return  # Probably a WebSocket connection

    if path == '/':
        path = '/index.html'

    response_headers = [
        ('Server', 'asyncio websocket server'),
        ('Connection', 'close'),
    ]

    # Derive full system path
    full_path = os.path.realpath(os.path.join("public", path[1:]))

    # Validate the path
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        print("HTTP GET {} 404 NOT FOUND".format(path))
        return HTTPStatus.NOT_FOUND, [], b'404 NOT FOUND'

    # Guess file content type
    mime_type = mimetypes.guess_type(full_path, "application/octet-stream")[0]
    response_headers.append(('Content-Type', mime_type))

    # Read the whole file into memory and send it out
    body = open(full_path, 'rb').read()
    response_headers.append(('Content-Length', str(len(body))))
    # print("HTTP GET {} 200 OK".format(path))
    return HTTPStatus.OK, response_headers, body

async def main():
    async with websockets.serve(handler, "", 8765, process_request=process_request):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
