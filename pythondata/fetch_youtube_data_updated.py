import os
import sqlite3
from datetime import datetime, UTC
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import isodate
import time
import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

# ----------------------------
# ENV + API SETUP
# ----------------------------

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")

CHANNELS = {
    1: "UC0O-1BLhHwOV-QYqnj-C0gw",
    2: "UCRQdsiFTVCH4n2tyGKd1szQ",
}

DB_FILE = "eotc_youtube_data.db"
YOUTUBE = build("youtube", "v3", developerKey=API_KEY)


# ----------------------------
# DATABASE SETUP
# ----------------------------


def setup_database():
    conn = sqlite3.connect(DB_FILE)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS channels (
            channel INTEGER PRIMARY KEY,
            channel_id TEXT,
            channel_title TEXT,
            subscribers INTEGER,
            total_views INTEGER,
            total_videos INTEGER,
            last_updated TEXT
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT,
            channel INTEGER,
            title TEXT,
            published_at TEXT,
            views INTEGER,
            likes INTEGER,
            comments INTEGER,
            duration_sec REAL,
            thumbnail_url TEXT,
            last_updated TEXT,
            PRIMARY KEY (video_id, channel)
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            author TEXT,
            comment TEXT,
            published_at TEXT,
            like_count INTEGER
        )
    """
    )

    conn.commit()
    return conn


# ----------------------------
# CHANNEL METADATA
# ----------------------------


def get_channel_stats(channel_id):
    r = YOUTUBE.channels().list(part="snippet,statistics", id=channel_id).execute()

    if not r["items"]:
        return None

    item = r["items"][0]
    stats = item.get("statistics", {})

    hidden = stats.get("hiddenSubscriberCount", False)

    return {
        "channel_id": channel_id,
        "channel_title": item["snippet"].get("title", ""),
        "subscribers": None if hidden else int(stats.get("subscriberCount", 0)),
        "total_views": int(stats.get("viewCount", 0)),
        "total_videos": int(stats.get("videoCount", 0)),
        "last_updated": datetime.now(UTC).isoformat(),
    }


# ----------------------------
# VIDEO HELPERS
# ----------------------------


def get_uploads_playlist_id(channel_id):
    r = YOUTUBE.channels().list(part="contentDetails", id=channel_id).execute()

    return r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


def get_all_video_ids(playlist_id):
    ids = []
    token = None

    while True:
        res = (
            YOUTUBE.playlistItems()
            .list(
                playlistId=playlist_id,
                part="contentDetails",
                maxResults=50,
                pageToken=token,
            )
            .execute()
        )

        for item in res["items"]:
            ids.append(item["contentDetails"]["videoId"])

        token = res.get("nextPageToken")
        if not token:
            break

    return ids


def get_video_stats(video_ids):
    rows = []

    for i in range(0, len(video_ids), 50):
        r = (
            YOUTUBE.videos()
            .list(
                part="snippet,statistics,contentDetails",
                id=",".join(video_ids[i : i + 50]),
            )
            .execute()
        )

        for item in r["items"]:
            sn = item["snippet"]
            st = item.get("statistics", {})
            cd = item.get("contentDetails", {})

            duration = cd.get("duration", "")
            parsed_duration = (
                isodate.parse_duration(duration).total_seconds() if duration else 0
            )

            rows.append(
                {
                    "video_id": item["id"],
                    "title": sn.get("title", ""),
                    "published_at": sn.get("publishedAt", ""),
                    "views": int(st.get("viewCount", 0)),
                    "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0)),
                    "duration_sec": parsed_duration,
                    "thumbnail_url": sn["thumbnails"].get("high", {}).get("url", ""),
                    "last_updated": datetime.now(UTC).isoformat(),
                }
            )

    return pd.DataFrame(rows)


# ----------------------------
# COMMENTS
# ----------------------------


def get_comments(video_id, comment_count):
    if comment_count == 0:
        return []

    comments = []
    token = None

    while True:
        try:
            r = (
                YOUTUBE.commentThreads()
                .list(
                    part="snippet",
                    videoId=video_id,
                    maxResults=100,
                    pageToken=token,
                    textFormat="plainText",
                )
                .execute()
            )

            for item in r.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]

                comments.append(
                    {
                        "video_id": video_id,
                        "author": snippet.get("authorDisplayName", ""),
                        "comment": snippet.get("textDisplay", ""),
                        "published_at": snippet.get("publishedAt", ""),
                        "like_count": int(snippet.get("likeCount", 0)),
                    }
                )

            token = r.get("nextPageToken")
            if not token:
                break

        except HttpError as e:
            if "commentsDisabled" in str(e):
                break
            elif "quotaExceeded" in str(e):
                time.sleep(60)
                continue
            else:
                break

    return comments


# ----------------------------
# DB HELPERS
# ----------------------------


def get_existing_video_ids(conn, channel_num):
    """Return the set of video IDs already stored in the DB for a given channel."""
    cursor = conn.execute(
        "SELECT video_id FROM videos WHERE channel = ?", (channel_num,)
    )
    return {row[0] for row in cursor.fetchall()}


def get_videos_with_comments(conn):
    """Return the set of video IDs that already have comments stored."""
    cursor = conn.execute("SELECT DISTINCT video_id FROM comments")
    return {row[0] for row in cursor.fetchall()}


# ----------------------------
# MAIN PIPELINE
# ----------------------------


def main():
    conn = setup_database()

    for channel_num, channel_code in CHANNELS.items():
        print(f"\n========== Channel {channel_num} ==========")

        # -------- Channel Metadata --------
        stats = get_channel_stats(channel_code)
        if stats:
            stats["channel"] = channel_num

            conn.execute(
                """
                INSERT OR REPLACE INTO channels
                (channel, channel_id, channel_title, subscribers, total_views, total_videos, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    channel_num,
                    stats["channel_id"],
                    stats["channel_title"],
                    stats["subscribers"],
                    stats["total_views"],
                    stats["total_videos"],
                    stats["last_updated"],
                ),
            )
            conn.commit()

        # -------- Videos --------
        playlist_id = get_uploads_playlist_id(channel_code)
        all_video_ids = get_all_video_ids(playlist_id)

        # Filter out videos already in the DB
        existing_ids = get_existing_video_ids(conn, channel_num)
        new_video_ids = [vid for vid in all_video_ids if vid not in existing_ids]

        print(f"Found {len(all_video_ids)} total videos, {len(new_video_ids)} new.")

        if not new_video_ids:
            print("No new videos to process. Skipping.")
            continue

        df_videos = get_video_stats(new_video_ids)
        df_videos["channel"] = channel_num

        for _, row in df_videos.iterrows():
            conn.execute(
                """
                INSERT OR REPLACE INTO videos
                (video_id, channel, title, published_at, views, likes, comments, duration_sec, thumbnail_url, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    row["video_id"],
                    channel_num,
                    row["title"],
                    row["published_at"],
                    row["views"],
                    row["likes"],
                    row["comments"],
                    row["duration_sec"],
                    row["thumbnail_url"],
                    row["last_updated"],
                ),
            )
        conn.commit()

        print(f"Inserted {len(df_videos)} new videos.")

        # -------- Comments --------
        # Also skip comment fetching for videos whose comments are already stored
        videos_with_comments = get_videos_with_comments(conn)
        df_new_comments = df_videos[~df_videos["video_id"].isin(videos_with_comments)]

        all_comments = []

        for _, row in tqdm(df_new_comments.iterrows(), total=len(df_new_comments)):
            all_comments.extend(get_comments(row["video_id"], row["comments"]))

        if all_comments:
            pd.DataFrame(all_comments).to_sql(
                "comments",
                conn,
                if_exists="append",
                index=False,
            )

        print(f"Added {len(all_comments)} comments.")

    conn.close()
    print("\n✅ Update complete.")


# ----------------------------
# RUN
# ----------------------------

if __name__ == "__main__":
    main()
