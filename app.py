import sys
import os
import re

import praw
import spotipy
import emoji

from flask import Flask, redirect, url_for, session, request, render_template, flash, jsonify
from spotipy import oauth2
from dotenv import load_dotenv
from nltk.corpus import stopwords 
from nltk.tokenize import word_tokenize 

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key'

SPOTIPY_CLIENT_ID = os.environ.get('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.environ.get('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.environ.get('SPOTIPY_REDIRECT_URI')

scope = ["playlist-modify-public", "playlist-modify-private", "user-read-email"]
spotify = oauth2.SpotifyOAuth(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI, scope=scope)

def create_reddit_client():
    return praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID"),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
        user_agent=os.environ.get("REDDIT_USERAGENT")
    )

reddit = create_reddit_client()

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login')
def login():
    auth_url = spotify.get_authorize_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = spotify.get_access_token(code)
    access_token = token_info['access_token']
    session['spotify_token'] = access_token
    # You can also store additional information from token_info if needed
    return redirect(url_for('create_playlist'))

def get_spotify_client(spotify_client=None):
    if 'spotify_token' in session:
        spotify_client = spotipy.Spotify(auth=session['spotify_token'])
        return spotify_client
    else:
        return redirect(url_for('login'))

def create_playlist_title_from_post_title(reddit, url):
    reddit_post = reddit.submission(url=url)
    reddit_post_title = reddit_post.title.lower().replace("?", "")
    stop_words = set(stopwords.words('english')) 
    word_tokens = word_tokenize(reddit_post_title) 
    filtered_sentence = [w for w in word_tokens if not w in stop_words] 
    return " ".join(filtered_sentence)

def find_and_add_songs_to_playlist(reddit_post_comments, spotify_client, playlist):
    reddit_post_comment_lines = [comment.body.split("\n") for comment in reddit_post_comments]
    possible_songs = [re.sub(r'http\S+', '', line) for comment in reddit_post_comment_lines for line in comment if line]
    possible_songs = [possible_song for possible_song in possible_songs if not possible_song == "["]
    possible_songs = [emoji.replace_emoji(possible_song, replace='') for possible_song in possible_songs]
    possible_songs = [possible_song for possible_song in possible_songs if not possible_song.isspace()]
    possible_songs = list(filter(None, possible_songs))
    results = [spotify_client.search(q=possible_song[:100], type='track', market=os.environ.get("SPOTIFY_MARKET", "US"), limit=1) for possible_song in possible_songs]
    song_ids = [result['tracks']['items'][0]['id'] for result in results if result['tracks']['items'] !=[]]
    song_ids = list(dict.fromkeys(song_ids))
    session['messages'].append(f"Adding songs to your playlist...")
    for index in range(0, len(song_ids), 100):
        spotify_client.user_playlist_add_tracks(os.environ.get("SPOTIFY_USER_ID"), playlist['id'], song_ids[index:index+100])

@app.route('/create/playlist', methods=('GET', 'POST'))
def create_playlist():
    spotify_client = get_spotify_client()
    user_info = spotify_client.current_user()
    if request.method == 'POST':
        session['messages'] = []
        url = request.form['url']
        session['messages'].append(f"Generating a name for your playlist...")
        playlist_name = create_playlist_title_from_post_title(reddit, url)
        session['messages'].append(f"Creating your playlist...")
        playlist = spotify_client.user_playlist_create(user_info['id'], playlist_name, public=True, description="Playlist created from Reddit comments: " + url)
        session['messages'].append(f"Fetching comments...")
        reddit_post_comments = reddit.submission(url=url).comments
        session['messages'].append(f"Finding songs from comments...")
        find_and_add_songs_to_playlist(reddit_post_comments, spotify_client, playlist)
        session['messages'] = []
        return redirect(url_for('success',  playlist_url=playlist['external_urls']['spotify']))
    return render_template('create_playlist.html')

@app.route('/success')
def success():
    playlist_url = request.args['playlist_url']
    token_info = spotify.get_cached_token()
    if spotify.is_token_expired(token_info):
        token_info = spotify.refresh_access_token(token_info['refresh_token'])
        session['spotify_token'] = token_info['access_token']
    spotify_client = get_spotify_client()
    username = spotify_client.current_user().get('display_name')
    return render_template('success.html', playlist_url=playlist_url, username=username)

@app.route('/logout')
def logout():
    session.pop('spotify_token', None)
    return redirect(url_for('index'))
    
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
