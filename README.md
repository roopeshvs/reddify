# Reddify

Reddify is a simple web utility to create Spotify Playlists out of Reddit posts.

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

## Installation

To install Reddify, you will need to have Python 3.8 or later installed on your machine. You can download Python from the [official website](https://www.python.org/downloads/).

Clone the repository to your local machine and install the required packages using pip:

```bash
git clone https://github.com/roopeshvs/reddify.git
cd reddify
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

You will need to create a Spotify Developer account and create a new application to get your client ID and client secret. You can do this by following the instructions [here](https://developer.spotify.com/documentation/general/guides/app-settings/).

You will also need to create a Reddit Developer account and create a new application to get your client ID and client secret. You can do this by following the instructions [here](https://www.reddit.com/prefs/apps).

Create a new file called `.env` in the root directory of the project and add the following lines:

```bash
SPOTIPY_CLIENT_ID=spotify-client-id
SPOTIPY_CLIENT_SECRET=spotify-client-secret
SPOTIPY_REDIRECT_URI=http://localhost:8091
REDDIT_CLIENT_ID=reddit-client-id
REDDIT_CLIENT_SECRET=reddit-client-secret
REDDIT_USER_AGENT=reddify.v1 by /u/your-reddit-username
```

Replace the above placeholders with your actual client ID, client secret, and Reddit username. Make sure to add the value for `SPOTIPY_REDIRECT_URI` in your Spotify application settings as well. 

## Usage

To run Reddify, you can use the following command:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8091
```

## Contributing

Contributions are welcome! Currently, the project is in its early stages and there are many features that could be added. If you would like to contribute, please follow these steps:

1. Open an issue to discuss the feature you would like to add.
2. Fork the project.
3. Create a new branch with a descriptive name.
4. Make your changes.
5. Open a pull request to `develop` with a description of your changes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
