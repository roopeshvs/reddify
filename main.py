import random
import math
import requests
import base64
import os
import asyncpraw as praw
import uuid
import json
import re
import emoji
import logging
import httpx
import uvicorn
from urllib.parse import urlencode
from typing import List
from fastapi import FastAPI, Response, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(levelname)-9s %(asctime)s - %(name)s - %(message)s")
LOGGER = logging.getLogger(__name__)

load_dotenv()

class HTTPXClientWrapper:

    async_client = None

    def start(self):
        """ Instantiate the client. Call from the FastAPI startup hook."""
        self.async_client = httpx.AsyncClient()
        LOGGER.info(f'httpx AsyncClient instantiated. Id {id(self.async_client)}')

    async def stop(self):
        """ Gracefully shutdown. Call from FastAPI shutdown hook."""
        LOGGER.info(f'httpx async_client.is_closed(): {self.async_client.is_closed} - Now close it. Id (will be unchanged): {id(self.async_client)}')
        await self.async_client.aclose()
        LOGGER.info(f'httpx async_client.is_closed(): {self.async_client.is_closed}. Id (will be unchanged): {id(self.async_client)}')
        self.async_client = None
        LOGGER.info('httpx AsyncClient closed')

    def __call__(self):
        """ Calling the instantiated HTTPXClientWrapper returns the wrapped singleton."""
        # Ensure we don't use it if not started / running
        assert self.async_client is not None
        # LOGGER.info(f'httpx async_client.is_closed(): {self.async_client.is_closed}. Id (will be unchanged): {id(self.async_client)}')
        return self.async_client

httpx_client_wrapper = HTTPXClientWrapper()
app = FastAPI()
templates = Jinja2Templates(directory="./templates")

STATE_KEY = "spotify_auth_state"
CLIENT_ID = os.environ["SPOTIFY_CLIENT_ID"]
CLIENT_SECRET = os.environ["SPOTIFY_CLIENT_SECRET"]
URI = os.environ["APPLICATION_URI"]
REDIRECT_URI = URI + "/callback"

MAX_RETRIES = 5

@app.on_event("startup")
async def startup_event():
    httpx_client_wrapper.start()


@app.on_event("shutdown")
async def shutdown_event():
    await httpx_client_wrapper.stop()

@app.get('/external')
async def call_external_api(url, method='GET', websocket=None, params=None, json=None):
    async_client = httpx_client_wrapper()
    access_token = websocket.cookies.get("accessToken")
    headers = {
        'Authorization': 'Bearer ' + access_token
    }
    if method == 'GET':
        response = await async_client.get(url, headers=headers, params=params)
    elif method == 'POST':
        response = await async_client.post(url, headers=headers, json=json)
    return response

def create_reddit_client():
    return praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID"),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
        user_agent=os.environ.get("REDDIT_USERAGENT")
    )


reddit = create_reddit_client()


def generate_random_string(string_length):
    possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    text = "".join(
        [
            possible[math.floor(random.random() * len(possible))]
            for i in range(string_length)
        ]
    )

    return text


@app.get("/login")
def read_root(response: Response):
    state = generate_random_string(20)

    scope = "playlist-modify-public playlist-modify-private user-read-email"

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "scope": scope,
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    response = RedirectResponse(
        url="https://accounts.spotify.com/authorize?" + urlencode(params)
    )
    response.set_cookie(key=STATE_KEY, value=state)
    return response


@app.get("/callback")
def callback(request: Request, response: Response):

    code = request.query_params["code"]
    state = request.query_params["state"]
    stored_state = request.cookies.get(STATE_KEY)

    if state == None or state != stored_state:
        raise HTTPException(status_code=400, detail="State mismatch")
    else:

        response.delete_cookie(STATE_KEY, path="/", domain=None)

        url = "https://accounts.spotify.com/api/token"
        request_string = CLIENT_ID + ":" + CLIENT_SECRET
        encoded_bytes = base64.b64encode(request_string.encode("utf-8"))
        encoded_string = str(encoded_bytes, "utf-8")
        header = {"Authorization": "Basic " + encoded_string}

        form_data = {
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        api_response = requests.post(url, data=form_data, headers=header)

        if api_response.status_code == 200:
            data = api_response.json()
            access_token = data["access_token"]
            refresh_token = data["refresh_token"]

            response = RedirectResponse(url=URI)
            response.set_cookie(key="accessToken", value=access_token)
            response.set_cookie(key="refreshToken", value=refresh_token)

        return response


@app.get("/", response_class=HTMLResponse)
def main(request: Request):

    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/refresh_token")
def refresh_token(request: Request):

    refresh_token = request.query_params["refresh_token"]
    request_string = CLIENT_ID + ":" + CLIENT_SECRET
    encoded_bytes = base64.b64encode(request_string.encode("utf-8"))
    encoded_string = str(encoded_bytes, "utf-8")
    header = {"Authorization": "Basic " + encoded_string}

    form_data = {"grant_type": "refresh_token", "refresh_token": refresh_token}

    url = "https://accounts.spotify.com/api/token"

    response = requests.post(url, data=form_data, headers=header)
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Error with refresh token")
    else:
        data = response.json()
        access_token = data["access_token"]

        return {"access_token": access_token}
    
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)
    
manager = ConnectionManager()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: uuid.UUID):
    await manager.connect(websocket)
    try:
        while True:
            url = await websocket.receive_text()
            market = await websocket.receive_text()
            url = re.sub(r"\?utm_source=.*", "", url)
            reddit_submission = await reddit.submission(url=url)
            message = {
                "status": f"Fetching messages from Reddit Post..."
            }
            await manager.send_personal_message(json.dumps(message), websocket)
            await reddit_submission.comments.replace_more(limit=None)
            for comment in reddit_submission.comments:
                # time.sleep(0.1)
                message = {
                    "message": f"{comment.body}"
                }
                await manager.send_personal_message(json.dumps(message), websocket)
            
            message = {
                "status": f"Creating Spotify Playlist..."
            }
            await manager.send_personal_message(json.dumps(message), websocket)
            playlist_name = reddit_submission.title
            
            access_token = websocket.cookies.get("accessToken")
            
            me_url = "https://api.spotify.com/v1/me"
            headers = {
                'Authorization': 'Bearer ' + access_token
            }
            me_response = await call_external_api(me_url, method='GET', websocket=websocket)
            user_id = me_response.json()["id"]
            display_name = me_response.json()["display_name"]

            access_token = websocket.cookies.get("accessToken")
            
            playlists_url = f"https://api.spotify.com/v1/users/{user_id}/playlists"
            data = {
                "name": playlist_name,
                "description": f"Playlist created from Reddit post: {url}"
            }
            playlists_response = await call_external_api(playlists_url, method='POST', websocket=websocket, json=data)
            print(playlists_response.json())
            playlist_id = playlists_response.json()["id"]
            playlist_url = playlists_response.json()["external_urls"]["spotify"]
            message = {
                "status": f"Playlist created. Finding songs..."
            }
            await manager.send_personal_message(json.dumps(message), websocket)

            track_uris = []
            filtered_lines = []
            all_comments = await reddit_submission.comments()
            for comment in all_comments:
                if comment.author is not None and comment.author.name != "AutoModerator" and comment.author.name != "Reddit":
                    lines = comment.body.splitlines()
                    for line in lines:
                        line = re.sub(r"http\S+", "", line)
                        line = emoji.replace_emoji(line, replace='')
                        if line is not None and line != "" and line != "[" and not line.isspace():
                            filtered_lines.append(line)
            for line in filtered_lines:
                search_url = "https://api.spotify.com/v1/search"
                search_params = {
                    "q": line[:100],
                    "type": "track",
                    "limit": 1,
                    "market": market if market else "US"
                }
                for _ in range(MAX_RETRIES):
                    try:
                        search_response = await call_external_api(search_url, method='GET', websocket=websocket, params=search_params)
                        print(search_response)
                    except (httpx._exceptions.ConnectError, httpx._exceptions.ReadTimeout) as e:
                        logging.error(f"Error: {e}. Retrying...")
                        continue
                    break
                else:
                    logging.error("Max retries exceeded. Skipping...")
                    continue
                search_response = search_response.json()
                if search_response.get("tracks") is not None and search_response["tracks"]["items"]:
                    track_name = search_response["tracks"]["items"][0]["name"]
                    artist_name = search_response["tracks"]["items"][0]["artists"][0]["name"]
                    track_uri = search_response["tracks"]["items"][0]["uri"]
                    track_uris.append(track_uri)
                    message = {
                        "message": f"{track_name} by {artist_name}"
                    }
                    await manager.send_personal_message(json.dumps(message), websocket)
                else:
                    logging.error(f"Could not find track for comment: {comment.body}")
            
            message = {
                "status": f"Adding songs to playlist..."
            }
            await manager.send_personal_message(json.dumps(message), websocket)
            track_uris = list(set(track_uris))
            add_tracks_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
            for i in range(0, min(len(track_uris), 10000), 100):
                data = {
                    "uris": track_uris[i:i+100]
                }
                for _ in range(MAX_RETRIES):
                    try:
                        await call_external_api(add_tracks_url, method='POST', websocket=websocket, json=data)
                    except (httpx._exceptions.ConnectError, httpx._exceptions.ReadTimeout) as e:
                        logging.error(f"Error: {e}. Retrying...")
                        continue
                    break
                else:
                    logging.error("Max retries exceeded when adding tracks to playlist. Skipping...")
                    continue

            message = {
                "status": f"Hooray! {display_name}, Your Playlist is ready!",
                "playlist_url": f"{playlist_url}"
            }
            await manager.send_personal_message(json.dumps(message), websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == '__main__':
    LOGGER.info(f'starting...')
    uvicorn.run(f"{__name__}:app", host="0.0.0.0", port=8091)
    