# Reddify

Reddify is a simple web utility to create a Spotify playlist out of a Reddit post's comments. 

## Installation

To install and run Reddify locally, follow these steps:

1. Clone the repository: `git clone https://github.com/roopeshvs/reddify.git`
2. Install the required dependencies: `pip install -r requirements` from the root directory.
3. Create a `.env` file at the root of the directory.
    ```
    REDDIT_CLIENT_ID=""
    REDDIT_CLIENT_SECRET=""
    REDDIT_USERAGENT=""
    SPOTIPY_CLIENT_ID=""
    SPOTIPY_CLIENT_SECRET=""
    SPOTIPY_REDIRECT_URI=""
    SPOTIFY_MARKET=""
    SECRET_KEY=""
    ```
4. Populate the environment variables.
    
- `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` - Register to use the Reddit API and create an application to receive both. More details at [https://www.reddit.com/wiki/api/](https://www.reddit.com/wiki/api/)
- `REDDIT_USERAGENT` - This is used by Reddit to identify your program.Example: User-Agent: reddify:v0.1 (by /u/<reddit-username>) [https://github.com/reddit-archive/reddit/wiki/API#rules](https://github.com/reddit-archive/reddit/wiki/API#rules)
- `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` - Register to use the Spotify Web API and create an application to receive both. More details at [https://developer.spotify.com/documentation/web-api](https://developer.spotify.com/documentation/web-api)
- `SPOTIPY_REDIRECT_URI` - When running locally, you can set this to [https://localhost:8888/callback](https://localhost:8888/callback). Make sure to add the same callback URL in your Spotify application as well.
- `SPOTIFY_MARKET` - This is optional. Must be one of the country codes from the list [here](https://developer.spotify.com/documentation/web-api/reference/get-available-markets). Defaults to `US`. This setting can help in identifying songs not in English.
- `SECRET_KEY` - This key is used to securely sign the session cookie. You can generate one using this command `python -c 'import secrets; print(secrets.token_hex())'`

4. Start the application: `python app.py`

## Note on usage

Reddit applications on mobile generate user-specific links in the pattern of https://www.reddit.com/r/<sub-reddit>/s/<random-characters> that link to the Reddit post. Reddit blocks bots from resolving this URL to find the expanded URL of the post, and therefore these links are not supported at the moment. For those on mobile, after copying the post URL, paste it on a browser to get the expanded URL.

## Contributing

Contributions are welcome! If you'd like to contribute to Reddify, please follow these steps:

1. Fork the repository
2. Create a new branch: `git checkout -b feature/your-feature-name`
3. Make your changes and commit them: `git commit -m 'Add some feature'`
4. Push to the branch: `git push origin feature/your-feature-name`
5. Open a pull request

Feel free to open a PR to start a discussion if your change is large.

## License

This project is licensed under the [MIT License](LICENSE).

## Contact

If you have any questions or suggestions, feel free to open an issue or reach out at [roopesh@mail.pesh.dev](mailto:roopesh@mail.pesh.dev).