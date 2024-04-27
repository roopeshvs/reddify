import os
import re

import praw
import spotipy
import emoji

from flask import Flask, redirect, url_for, session, request, render_template, flash, jsonify
from flask_session import Session
from spotipy import oauth2
from dotenv import load_dotenv
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

load_dotenv()

app = Flask(__name__)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './.flask_session/'
app.secret_key = os.environ.get('SECRET_KEY')
Session(app)

SPOTIPY_CLIENT_ID = os.environ.get('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.environ.get('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.environ.get('SPOTIPY_REDIRECT_URI')


def create_reddit_client():
    return praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID"),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
        user_agent=os.environ.get("REDDIT_USERAGENT")
    )


reddit = create_reddit_client()


def get_spotify_client():
    cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
    spotify = oauth2.SpotifyOAuth(cache_handler=cache_handler)
    if not spotify.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    return spotipy.Spotify(auth_manager=spotify)


@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login')
def login():
    cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
    scope = ["playlist-modify-public",
             "playlist-modify-private", "user-read-email"]
    spotify = oauth2.SpotifyOAuth(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET,
                                  SPOTIPY_REDIRECT_URI, cache_handler=cache_handler, scope=scope)
    auth_url = spotify.get_authorize_url()
    return redirect(auth_url)


@app.route('/callback')
def callback():
    code = request.args.get('code')
    cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
    spotify = oauth2.SpotifyOAuth(cache_handler=cache_handler)
    spotify.get_access_token(code)
    return redirect(url_for('create_playlist'))


def create_playlist_title_from_post_title(reddit, url):
    reddit_post = reddit.submission(url=url)
    reddit_post_title = reddit_post.title.lower().replace("?", "")
    stop_words = set(stopwords.words('english'))
    word_tokens = word_tokenize(reddit_post_title)
    filtered_sentence = [w for w in word_tokens if not w in stop_words]
    return " ".join(filtered_sentence)


def find_and_add_songs_to_playlist(reddit_post_comments, spotify_client, playlist):
    reddit_post_comment_lines = [comment.body.splitlines()
                                 for comment in reddit_post_comments]
    possible_songs = [re.sub(r'http\S+', '', line)
                      for comment in reddit_post_comment_lines for line in comment if line]
    possible_songs = [
        possible_song for possible_song in possible_songs if not possible_song == "["]
    possible_songs = [emoji.replace_emoji(
        possible_song, replace='') for possible_song in possible_songs]
    possible_songs = [
        possible_song for possible_song in possible_songs if not possible_song.isspace()]
    possible_songs = list(filter(None, possible_songs))
    results = [spotify_client.search(q=possible_song[:100], type='track', market=os.environ.get(
        "SPOTIFY_MARKET", "US"), limit=1) for possible_song in possible_songs]
    song_ids = [result['tracks']['items'][0]['id']
                for result in results if result['tracks']['items'] != []]
    song_ids = list(dict.fromkeys(song_ids))
    for index in range(0, len(song_ids), 100):
        spotify_client.user_playlist_add_tracks(os.environ.get(
            "SPOTIFY_USER_ID"), playlist['id'], song_ids[index:index+100])


@app.route('/create/playlist', methods=('GET', 'POST'))
def create_playlist():
    spotify_client = get_spotify_client()
    user_info = spotify_client.current_user()
    if request.method == 'POST':
        url = request.form['url']
        pattern = r"(https?://)?(www\.)?reddit\.com/r/[\w-]+/comments/[\w-]+/?"
        if not re.match(pattern, url):
            flash("""❗ Invalid URL pattern. 
                  If you copied the link from the Reddit mobile app, 
                  please paste the copied link in your browser to get the full URL.""", "error")
            return redirect(url_for('create_playlist'))
        try:
            playlist_name = create_playlist_title_from_post_title(reddit, url)
            playlist = spotify_client.user_playlist_create(
                user_info['id'], playlist_name, public=False, description="Playlist created from Reddit comments: " + url)
            reddit_post_comments = reddit.submission(url=url).comments
            find_and_add_songs_to_playlist(
                reddit_post_comments, spotify_client, playlist)
        except Exception as e:
            flash(
                "❗ Uh Oh! An unknown error has occurred. Please check the URL and try again.", "error")
            return redirect(url_for('create_playlist'))
        return redirect(url_for('success',  playlist_url=playlist['external_urls']['spotify']))
    return render_template('create_playlist.html')


@app.route('/success')
def success():
    playlist_url = request.args['playlist_url']
    spotify_client = get_spotify_client()
    username = spotify_client.current_user().get('display_name')
    return render_template('success.html', playlist_url=playlist_url, username=username)


@app.route('/logout')
def logout():
    session.pop("token_info", None)
    session.pop("spotify_token", None)
    session.pop("session", None)
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
