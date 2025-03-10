from flask import Flask, Response
import requests
import json
import time
import os
import base64
import uuid
import pysftp
from io import BytesIO

# This API was made to integrate the Everlasting Skins mod
# with the webhook functionality of the Forge Discord-Integration mod
# Iggy Villa (C) 2025

app = Flask(__name__)

# For local dev testing environment, use this path instead
# EVERLASTING_SKINS_PATH = "qfs_2/EverlastingSkins"
EVERLASTING_SKINS_PATH = "../quafuzzii-s2/qfs2_world/EverlastingSkins"


class NullNamespace:
    bytes = b''


def get_uuid_from_name(name):
    """
    For offline servers, a players UUID is generated via their username.
    This just does that but in Python.

    :param name: Players username
    :return: UUID of player in string
    """
    # IDE gets angry with the NullNamespace but it works!
    return str(uuid.uuid3(NullNamespace, f'OfflinePlayer:{name}'))


def get_from_visage(subject):
    resp = requests.get(
        f"https://visage.surgeplay.com/bust/256/{subject}.png",
        # As required by the Visage API
        headers={'User-Agent': 'QuafuzziiSkinAPI/1.0 (akawmv@gmail.com)'}
    )
    return resp


def get_mojang_skin_b64(url):
    """
    Gets a skin from Mojang and encodes it in base64.

    :param url: URL to 64x64 .png skin from Mojang
    :return: Base-64 encoded image (string)
    """
    resp = requests.get(url)

    return base64.b64encode(resp.content).decode('utf-8')


@app.route("/getskin/<name>")
def get_skin(name):
    print(f"+ skin for {name} requested")

    # Everlasting Skins requests with .png already
    # appended to the name, so we have to do this
    original_name = name[:-4]
    name = name.lower()[:-4]

    with open('cache.json', 'r') as f:
        cache = json.load(f)

    if name not in cache["usernames"]:
        # Put person in cache and the last time
        # their skin was cached if they're not in it yet
        print(f"+ cached {name}")
        cache["usernames"][name] = 0

        with open('cache.json', 'w') as f:
            json.dump(cache, f, indent=4)

    time_since_last_cache = time.time() - cache["usernames"][name]

    # Note that here we're caching the *render* of their avatar
    if time_since_last_cache > (60*10):
        print("+ been 10 mins since last cache, replacing skin")

        # Grab the users UUID from username (needed to get correct EverlastingSkins .json)
        user_uuid = get_uuid_from_name(original_name)

        # SETUP SFTP CONNECTION

        # THIS IS INCREDIBLY UNSAFE! I'm just lazy.
        #  Usually SFTP will need an SSH host key to verify the connection,
        #  this bypasses that requirement completely. NOT GOOD!
        cnopts = pysftp.CnOpts()
        cnopts.hostkeys = None

        # Not happy with the speed of SFTP, this file transfer takes ~5 seconds on avg
        with pysftp.Connection(
                host=os.environ['SFTP_HOST'],
                port=60002,
                username=os.environ['SFTP_USR'],
                password=os.environ['SFTP_PW'],
                cnopts=cnopts
        ) as sftp:
            with sftp.cd("qfs4_world/EverlastingSkins"):
                if user_uuid + ".json" not in sftp.listdir("."):
                    # If Discord-Integration requests a player that hasn't
                    # been processed by EverlastingSkins yet
                    skin_data = 'X-Steve'
                else:
                    # Get players .json to get their associated skin_url
                    buf = BytesIO()
                    sftp.getfo(f'{user_uuid}.json', flo=buf)

                    player_info = json.loads(buf.getvalue().decode('utf-8'))
                    skinurl = json.loads(
                        base64.b64decode(player_info["value"]).decode('utf-8')
                    )["textures"]["SKIN"]["url"]
                    skin_data = get_mojang_skin_b64(skinurl)

        # Request the renderer API to render the players skin
        # it accepts either a default skin (like X-Steve) or
        # the base64-encoded .png file
        resp = get_from_visage(skin_data)
        print(f"+ resp from visage - {resp.status_code}")
        img_data = resp.content

        # Update cache
        cache["skinRender"][name] = base64.b64encode(resp.content).decode('utf-8')
        cache["usernames"][name] = time.time()

        with open('cache.json', 'w') as f:
            json.dump(cache, f)

        print(f"+ updated time since last_time & skin_render cache for {name}")
    else:
        # If skin_render already cached
        print(f"+ been less 5 mins since last render cache, using that")
        img_data = base64.b64decode(cache["skinRender"][name])

    return Response(img_data, headers={'Content-Type': 'image/png'})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=13571)
