# StravaBook
#
# Copyright (C) 2025  Laurent Burais
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the Affero GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#

"""
Package to export Strava data
"""

# pylint: disable=C0301,W0718,C0114,C0103
# flake8: noqa=E501

# ---------------------------------------------------------------------------------------------------------------------------------
#
# Used Python Modules
#
# ---------------------------------------------------------------------------------------------------------------------------------

import os
import time
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import webbrowser
import threading

import requests

# ---------------------------------------------------------------------------------------------------------------------------------
#
# Flask
#
# ---------------------------------------------------------------------------------------------------------------------------------


from flask import Flask, redirect, request, session, url_for, render_template

# Flask App Config
app = Flask(__name__)
app.secret_key = "your_secret_key"  # Change this!

# ---------------------------------------------------------------------------------------------------------------------------------
#
# Strava
#
# ---------------------------------------------------------------------------------------------------------------------------------


# Strava API Credentials
CLIENT_ID = "41263"
CLIENT_SECRET = "071510aead115e19759a4302241776a7652e07f9"
REDIRECT_URI = "http://127.0.0.1:5000/callback"

# Strava API Endpoints
PHOTO_SIZE = "5000"  # fake > max resolution
AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
PHOTO_URL_TEMPLATE = "https://www.strava.com/api/v3/activities/{}" + f"/photos?size={PHOTO_SIZE}&photo_sources=true"

# Directories

ACTIVITIES_DIR = "activities"
PHOTOS_DIR = "photos"

# ---------------------------------------------------------------------------------------------------------------------------------
# display
# ---------------------------------------------------------------------------------------------------------------------------------


def display(new_line):
    """
    Print log
    """

    print(new_line)
    # yield new_line

# ---------------------------------------------------------------------------------------------------------------------------------
# requests_get
# ---------------------------------------------------------------------------------------------------------------------------------


def requests_get(*args, **kwargs):
    """
    Get Strava API ensuring rate limits are respected.
    """

    while True:

        now_utc = datetime.now(ZoneInfo("UTC"))
        midnight_utc = datetime.now(ZoneInfo("UTC")).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        now = datetime.now()
        next_quarter_minute = (now.minute // 15 + 1) * 15
        if next_quarter_minute == 60:
            next_quarter = now.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)
        else:
            next_quarter = now.replace(minute=next_quarter_minute, second=0, microsecond=0)
        sleep_time = 0

        response = requests.get(*args, **kwargs)  # pylint: disable=W3101
        if 'x-ratelimit-usage' in response.headers:
            display(f"--> [usage : {response.headers['x-ratelimit-usage']}]")
        if response.status_code == 429:  # Too many requests
            if 'x-ratelimit-usage' in response.headers:
                usage = tuple(map(int, response.headers['x-ratelimit-usage'].split(",")))

                if usage[0] >= 100:
                    sleep_time = int((next_quarter - now).total_seconds())  # wait until next quarter
                elif usage[1] >= 1000:
                    sleep_time = int((midnight_utc - now_utc).total_seconds())  # wait until midnight
            else:
                sleep_time = int((midnight_utc - now_utc).total_seconds())  # wait until midnight

            hours = f"{int(sleep_time // 3600):d}h " if (sleep_time // 3600) > 0 else ""
            minutes = f"{int((sleep_time % 3600) // 60):d}mn " if ((sleep_time % 3600) // 60) > 0 else ""
            seconds = f"{int(sleep_time % 60):d}s"
            display(f"Too many requests. Sleeping for {hours}{minutes}{seconds} ...")

            time.sleep(sleep_time)
        else:
            break

    return response

# ---------------------------------------------------------------------------------------------------------------------------------
# get_access_token
# ---------------------------------------------------------------------------------------------------------------------------------


def get_access_token():
    """
    Get or refresh Strava access token.
    """

    if "access_token" not in session or time.time() > session.get("expires_at", 0):

        refresh_token = session.get("refresh_token")

        if not refresh_token:
            return None

        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=20
        ).json()

        session.update({
            "access_token": response.get("access_token"),
            "expires_at": response.get("expires_at"),
            "refresh_token": response.get("refresh_token"),
        })

    return session.get("access_token")

# ---------------------------------------------------------------------------------------------------------------------------------
# route /
# ---------------------------------------------------------------------------------------------------------------------------------


@app.route("/")
def home():
    """
    Landing page.
    """

    return render_template("index.html")

# ---------------------------------------------------------------------------------------------------------------------------------
# route /login
# ---------------------------------------------------------------------------------------------------------------------------------


@app.route("/login")
def login():
    """
    Redirect to Strava authorization page.
    """

    return redirect(
        f"{AUTH_URL}?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
        f"&response_type=code&scope=activity:read_all"
    )

# ---------------------------------------------------------------------------------------------------------------------------------
# route /
# ---------------------------------------------------------------------------------------------------------------------------------


@app.route("/callback")
def callback():
    """
    Handle Strava OAuth callback.
    """

    code = request.args.get("code")

    if not code:
        return "Authorization failed", 400

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=20
    ).json()

    session.update({
        "access_token": response.get("access_token"),
        "refresh_token": response.get("refresh_token"),
        "expires_at": response.get("expires_at"),
    })

    return render_template("index.html")

# ---------------------------------------------------------------------------------------------------------------------------------
# route /activities/{id}
# ---------------------------------------------------------------------------------------------------------------------------------


@app.route("/activity/<int:activity_id>")
def get_activity(activity_id):
    """
    Get a specific activity and fetch its photos.
    """

    display(f"{activity_id}")

# ---------------------------------------------------------------------------------------------------------------------------------
# route /collect
# ---------------------------------------------------------------------------------------------------------------------------------


@app.route("/collect")
def collect():
    """
    Fetch activities, save each one in JSON, download photos, and display.
    """

    access_token = get_access_token()
    if not access_token:
        return redirect(url_for("login"))

    page = 1
    per_page = 50

    while True:

        display(f"Fetching activities page {page}: {ACTIVITIES_URL}")

        # process page

        response = requests_get(
            ACTIVITIES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"per_page": per_page, "page": page},
            timeout=20
        )

        if response.status_code == 200:

            activities = response.json()

            if not activities:
                break

            # process activities

            for activity in activities:

                activity_id = activity.get("id")

                if activity.get("total_photo_count") > 0:

                    # Fetch photos
                    try:
                        display(f"- Fetching photos : {PHOTO_URL_TEMPLATE.format(activity_id)}")

                        photos = []

                        # get list from activity file
                        activity_filename = f"{ACTIVITIES_DIR}/{activity_id}.json"
                        if os.path.exists(activity_filename):

                            with open(activity_filename, "r", encoding='utf-8') as file:
                                data = json.load(file)

                            if 'urls' in data:
                                photos = data['urls']

                        # get list from API if missing photos
                        if len(photos) < activity.get("total_photo_count"):
                            response = requests_get(
                                f"{PHOTO_URL_TEMPLATE.format(activity_id)}",
                                headers={"Authorization": f"Bearer {access_token}"},
                                timeout=20
                            ).json()

                            # Extract valid image URLs from the response
                            photos = [
                                photo["urls"][PHOTO_SIZE]
                                for photo in response
                                if "urls" in photo and PHOTO_SIZE in photo["urls"] and not photo.get("is_default")
                            ]

                        activity["urls"] = photos

                    except Exception as e:
                        display(f"   Error downloading photos {activity_id}: {e}")

                    # Save photos locally
                    saved_photos = []
                    for i, photo_url in enumerate(photos):
                        photo_filename = f"{PHOTOS_DIR}/{activity_id}_{i}.jpg"

                        try:
                            if os.path.exists(photo_filename):
                                display(f"   - Photo : {photo_filename}")
                            else:
                                display(f"   - Dowloading photo : {photo_url}")

                                response = requests_get(photo_url, stream=True, timeout=20)

                                if response.status_code == 200:
                                    os.makedirs(os.path.dirname(photo_filename), exist_ok=True)
                                    with open(photo_filename, "wb") as file:
                                        for chunk in response.iter_content(1024):
                                            file.write(chunk)

                                    display(f"     Photo saved: {photo_filename}")
                                else:
                                    display(f"     Failed to download {photo_url}")

                        except Exception as e:
                            display(f"     Error photo {photo_url} : {e}")

                        saved_photos.append(photo_filename)

                    # Store photo paths in the activity
                    activity["photo_local_paths"] = saved_photos

                # Write activity JSON
                activity_filename = f"{ACTIVITIES_DIR}/{activity_id}.json"
                os.makedirs(os.path.dirname(activity_filename), exist_ok=True)
                with open(activity_filename, "w", encoding='utf-8') as file:
                    json.dump(activity, file, indent=4)

            page += 1

        else:
            display(f"Error fetching activities : {response.reason}")

    return render_template("activities.html", activities=response)


# ---------------------------------------------------------------------------------------------------------------------------------
# route /book
# ---------------------------------------------------------------------------------------------------------------------------------


@app.route("/book")
def book():
    """
    Create PDF book.
    """

    return render_template("index.html")

# ---------------------------------------------------------------------------------------------------------------------------------
# route /pdf
# ---------------------------------------------------------------------------------------------------------------------------------


@app.route("/pdf")
def pdf():
    """
    Open PDF book.
    """

    return render_template("index.html")

# ---------------------------------------------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------------------------------------------


if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.get("safari").open("http://127.0.0.1:5000")).start()
    app.run(debug=True, use_reloader=False)
