import sys
import os
import re

import praw
import spotipy
import emoji

from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
from nltk.corpus import stopwords 
from nltk.tokenize import word_tokenize 

load_dotenv()

def create_reddit_client():
    return praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID"),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
        user_agent=os.environ.get("REDDIT_USERAGENT")
    )

def create_spotify_client():
    scope = ["playlist-modify-public", "playlist-modify-private"]
    return spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))

def get_reddit_thread():
    if len(sys.argv) < 2:
        print("Please provide the Reddit post URL as a command line argument.")
        print("Usage: python run.py <Reddit post URL>")
        exit(1)
    reddit_url = sys.argv[1]
    pattern = r"(https?://)?(www\.)?reddit\.com/r/[\w-]+/comments/[\w-]+/?"
    if not re.match(pattern, reddit_url):
        print("Invalid Reddit post URL.")
        exit(1)
    return reddit_url

def create_playlist_title_from_post_title(reddit, thread, spotify):
    reddit_post = reddit.submission(url=thread)
    reddit_post_title = reddit_post.title.lower().replace("?", "")
    stop_words = set(stopwords.words('english')) 
    word_tokens = word_tokenize(reddit_post_title) 
    filtered_sentence = [w for w in word_tokens if not w in stop_words] 
    return " ".join(filtered_sentence)

def find_and_add_songs_to_playlist(reddit_post_comments, spotify, playlist):
    reddit_post_comment_lines = [comment.body.split("\n") for comment in reddit_post_comments]
    possible_songs = [re.sub(r'http\S+', '', line) for comment in reddit_post_comment_lines for line in comment if line]
    possible_songs = [possible_song for possible_song in possible_songs if not possible_song == "["]
    possible_songs = [emoji.replace_emoji(possible_song, replace='') for possible_song in possible_songs]
    possible_songs = [possible_song for possible_song in possible_songs if not possible_song.isspace()]
    possible_songs = list(filter(None, possible_songs))
    results = [spotify.search(q=possible_song[:100], type='track', market=os.environ.get("SPOTIFY_MARKET", "US"), limit=1) for possible_song in possible_songs]
    song_ids = [result['tracks']['items'][0]['id'] for result in results if result['tracks']['items'] !=[]]
    song_ids = list(dict.fromkeys(song_ids))
    for index in range(0, len(song_ids), 100):
        spotify.user_playlist_add_tracks(os.environ.get("SPOTIFY_USER_ID"), playlist['id'], song_ids[index:index+100])
    print(f"Playlist {playlist['name']} created from Reddit comments thread successfully. Enjoy!")

def main():
    thread = get_reddit_thread()
    reddit = create_reddit_client()
    spotify = create_spotify_client()
    playlist_name = create_playlist_title_from_post_title(reddit, thread, spotify)
    playlist = spotify.user_playlist_create(os.environ.get("SPOTIFY_USER_ID"), playlist_name, public=True, description="Playlist created from Reddit comments thread: " + thread)
    reddit_post_comments = reddit.submission(url=thread).comments
    find_and_add_songs_to_playlist(reddit_post_comments, spotify, playlist)

if __name__ == "__main__":
    main()
