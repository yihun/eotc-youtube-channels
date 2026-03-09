import os
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import isodate
import time
import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm
from sqlalchemy import create_engine, text
import re
import psycopg2  # noqa: F401

# ----------------------------
# ENV + API SETUP
# ----------------------------
load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")  # Neon/Postgres connection string

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables!")

# Only process channel 2 (skip channel 1)
CHANNELS = {2: "UCRQdsiFTVCH4n2tyGKd1szQ"}

YOUTUBE = build("youtube", "v3", developerKey=API_KEY)
engine = create_engine(DATABASE_URL)


# ----------------------------
# DATABASE HELPERS
# ----------------------------
def setup_database():
    with engine.connect() as conn:

        conn.execute(
            text(
                """
        CREATE TABLE IF NOT EXISTS channels (
            channel INTEGER PRIMARY KEY,
            channel_id TEXT,
            channel_title TEXT,
            subscribers INTEGER,
            total_views INTEGER,
            total_videos INTEGER,
            last_updated TIMESTAMP
        )
        """
            )
        )

        conn.execute(
            text(
                """
        CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT,
            channel INTEGER,
            title TEXT,
            published_at TIMESTAMP,
            views INTEGER,
            likes INTEGER,
            comments INTEGER,
            duration_sec REAL,
            thumbnail_url TEXT,
            last_updated TIMESTAMP,
            PRIMARY KEY (video_id, channel)
        )
        """
            )
        )

        conn.execute(
            text(
                """
        CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            video_id TEXT,
            author TEXT,
            comment TEXT,
            published_at TIMESTAMP,
            like_count INTEGER
        )
        """
            )
        )

        conn.commit()


def clean_text(x):
    if isinstance(x, str):
        return re.sub(r"[\x00-\x1F\x7F]", "", x)
    return x


# ----------------------------
# YOUTUBE HELPERS
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
        "last_updated": datetime.now(timezone.utc),
    }


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
        for item in res.get("items", []):
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
        for item in r.get("items", []):
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
                    "last_updated": datetime.now(timezone.utc),
                }
            )
    return pd.DataFrame(rows)


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
                sn = item["snippet"]["topLevelComment"]["snippet"]
                comments.append(
                    {
                        "video_id": video_id,
                        "author": sn.get("authorDisplayName", ""),
                        "comment": sn.get("textDisplay", ""),
                        "published_at": sn.get("publishedAt", ""),
                        "like_count": int(sn.get("likeCount", 0)),
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
# DB QUERY HELPERS
# ----------------------------
def get_existing_video_ids(channel_num):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT video_id FROM videos WHERE channel = :channel"),
            {"channel": channel_num},
        )
        return {row[0] for row in result.fetchall()}


def get_videos_with_comments(video_ids):
    if not video_ids:
        return set()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT DISTINCT video_id FROM comments WHERE video_id = ANY(:ids)"),
            {"ids": list(video_ids)},
        )
        return {row[0] for row in result.fetchall()}


# ----------------------------
# DB UPSERT HELPERS
# ----------------------------
def upsert_channel(channel_num, stats):
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO channels (channel, channel_id, channel_title, subscribers, total_views, total_videos, last_updated)
                VALUES (:channel, :channel_id, :channel_title, :subscribers, :total_views, :total_videos, :last_updated)
                ON CONFLICT (channel) DO UPDATE SET
                    channel_title = EXCLUDED.channel_title,
                    subscribers   = EXCLUDED.subscribers,
                    total_views   = EXCLUDED.total_views,
                    total_videos  = EXCLUDED.total_videos,
                    last_updated  = EXCLUDED.last_updated
            """
            ),
            {
                "channel": channel_num,
                "channel_id": stats["channel_id"],
                "channel_title": stats["channel_title"],
                "subscribers": stats["subscribers"],
                "total_views": stats["total_views"],
                "total_videos": stats["total_videos"],
                "last_updated": stats["last_updated"],
            },
        )
        conn.commit()


def upsert_videos(df_videos):
    with engine.connect() as conn:
        for record in df_videos.to_dict(orient="records"):
            conn.execute(
                text(
                    """
                    INSERT INTO videos (video_id, channel, title, published_at, views, likes, comments, duration_sec, thumbnail_url, last_updated)
                    VALUES (:video_id, :channel, :title, :published_at, :views, :likes, :comments, :duration_sec, :thumbnail_url, :last_updated)
                    ON CONFLICT (video_id, channel) DO UPDATE SET
                        title        = EXCLUDED.title,
                        views        = EXCLUDED.views,
                        likes        = EXCLUDED.likes,
                        comments     = EXCLUDED.comments,
                        last_updated = EXCLUDED.last_updated
                """
                ),
                record,
            )
        conn.commit()


# ----------------------------
# MAIN PIPELINE
# ----------------------------
def main():
    setup_database()

    for channel_num, channel_code in CHANNELS.items():
        print(f"\n========== Channel {channel_num} ==========")

        # --- Channel metadata ---
        stats = get_channel_stats(channel_code)
        if stats:
            upsert_channel(channel_num, stats)
            print(f"Upserted channel metadata for '{stats['channel_title']}'.")

        # --- Videos ---
        playlist_id = get_uploads_playlist_id(channel_code)
        all_video_ids = get_all_video_ids(playlist_id)
        existing_ids = get_existing_video_ids(channel_num)
        new_video_ids = [v for v in all_video_ids if v not in existing_ids]

        print(f"Found {len(all_video_ids)} videos, {len(new_video_ids)} new.")

        df_videos = pd.DataFrame()
        if new_video_ids:
            df_videos = get_video_stats(new_video_ids)
            df_videos["channel"] = channel_num
            upsert_videos(df_videos)
            print(f"Inserted/updated {len(df_videos)} videos.")

        # --- Comments ---
        videos_with_comments = get_videos_with_comments(all_video_ids)
        videos_needing_comments = [
            vid for vid in all_video_ids if vid not in videos_with_comments
        ]

        print(f"{len(videos_needing_comments)} videos still need comments.")

        all_comments = []
        for vid in tqdm(videos_needing_comments):
            comment_count = 0
            if not df_videos.empty:
                row = df_videos[df_videos["video_id"] == vid]
                if not row.empty:
                    comment_count = int(row.iloc[0]["comments"])
            all_comments.extend(get_comments(vid, comment_count))

        if all_comments:
            df_comments = pd.DataFrame(all_comments)
            for col in ["author", "comment"]:
                df_comments[col] = df_comments[col].apply(clean_text)
            df_comments.to_sql(
                "comments", engine, if_exists="append", index=False, method="multi"
            )

        print(f"Added {len(all_comments)} comments.")

    print("\n✅ Update complete.")


# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    main()
