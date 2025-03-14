from flask import Flask, redirect, request, session, url_for, render_template, jsonify
import requests
import os
import json

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Strava API Credentials
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REDIRECT_URI = "http://localhost:5000/callback"

# Strava API Endpoints
AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
PHOTO_URL_TEMPLATE = "https://www.strava.com/api/v3/activities/{}/photos"

# Ensure photo folder exists
os.makedirs("photos", exist_ok=True)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login")
def login():
    """Redirect to Strava authorization page."""
    return redirect(
        f"{AUTH_URL}?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
        f"&response_type=code&scope=activity:read_all"
    )


@app.route("/callback")
def callback():
    """Handle Strava OAuth callback."""
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
    ).json()

    session["access_token"] = response.get("access_token")
    return redirect(url_for("activities"))


@app.route("/activities")
def activities():
    """Fetch all activities and show them in the list box."""
    access_token = session.get("access_token")
    if not access_token:
        return redirect(url_for("login"))

    response = requests.get(
        ACTIVITIES_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"per_page": 10},
    ).json()

    # Save activities to a file
    with open("data/activities.json", "w") as file:
        json.dump(response, file, indent=4)

    return render_template("activities.html", activities=response)


@app.route("/activity/<int:activity_id>")
def get_activity(activity_id):
    """Get a specific activity and fetch its photos."""
    access_token = session.get("access_token")
    if not access_token:
        return redirect(url_for("login"))

    # Get activity details
    response = requests.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    # Get photos for this activity
    photos_response = requests.get(
        f"{PHOTO_URL_TEMPLATE.format(activity_id)}?photo_sources=true",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    photos = [
        photo["urls"]["600"]
        for photo in photos_response
        if "urls" in photo and "600" in photo["urls"] and not photo.get("is_default")
    ]

    return jsonify({"activity": response, "photos": photos})


if __name__ == "__main__":
    app.run(debug=True)
