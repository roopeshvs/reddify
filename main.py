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
import asyncio
from urllib.parse import urlencode
from typing import List
from fastapi import FastAPI, Response, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from asyncprawcore.exceptions import TooManyRequests, NotFound, ServerError

logging.basicConfig(level=logging.WARN, format="%(levelname)-9s %(asctime)s - %(name)s - %(message)s")
LOGGER = logging.getLogger(__name__)

load_dotenv()

class HTTPXClientWrapper:
    """ Singleton wrapper for the HTTPX AsyncClient."""
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
        assert self.async_client is not None
        LOGGER.debug(f'httpx async_client.is_closed(): {self.async_client.is_closed}. Id (will be unchanged): {id(self.async_client)}')
        return self.async_client

class WebsocketConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

httpx_client_wrapper = HTTPXClientWrapper()
ws_manager = WebsocketConnectionManager()
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
    """ Calls spotify API with access token. 
        Refreshes token if 401 and tries again."""
    async_client = httpx_client_wrapper()
    access_token = websocket.cookies.get("accessToken")
    headers = {
        'Authorization': 'Bearer ' + access_token
    }
    if method == 'GET':
        response = await async_client.get(url, headers=headers, params=params)
    elif method == 'POST':
        headers_1 = {
        'Authorization': 'Bearer ' + access_token + "123"
    }
        response = await async_client.post(url, headers=headers_1, json=json)
    if response.status_code == 401:
        LOGGER.info(f"Access token expired. Refreshing token...")
        refresh_token = websocket.cookies.get("refreshToken")
        request_string = CLIENT_ID + ":" + CLIENT_SECRET
        encoded_bytes = base64.b64encode(request_string.encode("utf-8"))
        encoded_string = str(encoded_bytes, "utf-8")
        header = {"Authorization": "Basic " + encoded_string}
        form_data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        refresh_token_url = "https://accounts.spotify.com/api/token"
        api_response = requests.post(refresh_token_url, data=form_data, headers=header)
        print(api_response.json(), api_response.status_code)
        if api_response.status_code == 200:
            LOGGER.info(f"Token refreshed successfully.")
            data = api_response.json()
            access_token = data["access_token"]
            response = RedirectResponse(url=URI)
            if data.get("refesh_token") is not None:
                refresh_token = data["refresh_token"]
            websocket.cookies["accessToken"] = access_token
            headers = {
                'Authorization': 'Bearer ' + access_token
            }
            if method == 'GET':
                response = await async_client.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = await async_client.post(url, headers=headers, json=json)
    return response

async def create_reddit_client():
    LOGGER.debug("Creating Async Reddit client...")
    return praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID"),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
        user_agent=os.environ.get("REDDIT_USERAGENT")
    )

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

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse("templates/favicon.ico")

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

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: uuid.UUID):
    await ws_manager.connect(websocket)
    try:
        while True:
            url = await websocket.receive_text()
            market = await websocket.receive_text()
            url = re.sub(r"\?utm_source=.*", "", url)
            reddit = await create_reddit_client()
            try:
                reddit_submission = await reddit.submission(url=url)
            except (NotFound, ServerError):
                message = {
                    "status": f"Invalid URL. Please enter a valid Reddit Post URL."
                }
                await ws_manager.send_message(json.dumps(message), websocket)
                await websocket.close(code=1000)
                return
            message = {
                "status": f"Fetching messages from Reddit Post..."
            }
            await ws_manager.send_message(json.dumps(message), websocket)
            comments = await reddit_submission.comments()
            for i in range(1, MAX_RETRIES+1):
                try:
                    await comments.replace_more(limit=None)
                    break
                except TooManyRequests as e:
                    LOGGER.warn(f"{client_id} - Error: {e}. Reddit API rate limit exceeded. Waiting for {i*2} minutes before trying again...")
                    message = {
                        "status": f"Reddit API rate limit exceeded. Waiting for {i*2} minutes before trying again..."
                    }
                    await ws_manager.send_message(json.dumps(message), websocket)
                    await asyncio.sleep(i*2*60)
                    message = {
                        "status": f"Fetching messages from Reddit Post..."
                    }
                    await ws_manager.send_message(json.dumps(message), websocket)
                    continue
                except Exception as e:
                    LOGGER.error(f"{client_id} - Error: {e}. Retrying...")
                    continue
            else:
                LOGGER.error(f"{client_id} - Max retries exceeded. Giving up...")
                message = {
                        "status": f"Coudn't fetch messages from Reddit Post at the moment. Please try again later."
                }
                await ws_manager.send_message(json.dumps(message), websocket)
                await websocket.close(code=1000)
                return
            message = {
                "status": f"Creating Spotify Playlist..."
            }
            await ws_manager.send_message(json.dumps(message), websocket)
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
            LOGGER.info(playlists_response.json())
            playlist_id = playlists_response.json()["id"]
            playlist_url = playlists_response.json()["external_urls"]["spotify"]
            message = {
                "status": f"Playlist created. Finding songs..."
            }
            await ws_manager.send_message(json.dumps(message), websocket)

            track_uris = []
            filtered_lines = []
            all_comments = await reddit_submission.comments()
            for comment in all_comments:
                """
                Skips AutoModerator and Reddit comments.
                Skips comments that contains images as the text accompanying the image usually doesn't contain song names.
                Removes all URLs from the comment at the moment. Should be improved to get the song name from spotify links at least. 
                Removes all emojis.
                """
                if comment.author is not None and comment.author.name != "AutoModerator" and comment.author.name != "Reddit" and "i.redd.it" not in comment.body:
                    lines = comment.body.splitlines()
                    for line in lines:
                        line = re.sub(r"http\S+", "", line)
                        line = emoji.replace_emoji(line, replace='')
                        if line is not None and line != "" and line != "[" and not line.isspace():
                            filtered_lines.append(line)
            for line in filtered_lines:
                search_url = "https://api.spotify.com/v1/search"
                search_params = {
                    "q": line[:100], # Spotify API allows only 100 characters in the query.
                    "type": "track",
                    "limit": 1,
                    "market": market if market else "US"
                }
                for _ in range(MAX_RETRIES):
                    try:
                        search_response = await call_external_api(search_url, method='GET', websocket=websocket, params=search_params)
                    except (httpx._exceptions.ConnectError, httpx._exceptions.ReadTimeout) as e:
                        LOGGER.error(f"{client_id} - Error: {e}. Retrying...")
                        continue
                    break
                else:
                    LOGGER.error(f"{client_id} - Max retries exceeded. Skipping...")
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
                    await ws_manager.send_message(json.dumps(message), websocket)
                else:
                    LOGGER.error(f"{client_id} - Could not find track for comment: {line[:100]}")
            
            message = {
                "status": f"Adding songs to playlist..."
            }
            await ws_manager.send_message(json.dumps(message), websocket)
            track_uris = list(set(track_uris))
            add_tracks_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
            for i in range(0, min(len(track_uris), 10000), 100):
                """
                Spotify API allows adding 100 tracks at a time.
                Spotify API allows adding 10,000 tracks to a playlist.
                """
                data = {
                    "uris": track_uris[i:i+100]
                }
                for _ in range(MAX_RETRIES):
                    try:
                        await call_external_api(add_tracks_url, method='POST', websocket=websocket, json=data)
                    except (httpx._exceptions.ConnectError, httpx._exceptions.ReadTimeout) as e:
                        LOGGER.error(f"{client_id} - Error: {e}. Retrying...")
                        continue
                    break
                else:
                    LOGGER.error(f"{client_id} - Max retries exceeded when adding tracks to playlist. Skipping...")
                    continue

            message = {
                "status": f"Hooray! {display_name}, Your Playlist is ready!",
                "playlist_url": f"{playlist_url}"
            }
            await ws_manager.send_message(json.dumps(message), websocket)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

if __name__ == '__main__':
    LOGGER.info(f'starting...')
    uvicorn.run(f"{__name__}:app", host="0.0.0.0", port=8091)
    
