import os
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

def get_latest_video_id(api_key: str, channel_handle: str = "@doppelgaengerio") -> dict:
    """
    Fetches the latest video ID and title from a YouTube channel handle.
    Returns: {"video_id": "...", "title": "..."}
    """
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        
        # 1. First, search for the channel ID using the handle
        channel_search = youtube.search().list(
            part="snippet",
            q=channel_handle,
            type="channel",
            maxResults=1
        ).execute()
        
        if not channel_search.get("items"):
            return {"error": f"Channel {channel_handle} not found."}
            
        channel_id = channel_search["items"][0]["snippet"]["channelId"]
        
        # 2. Get the latest video for this channel
        video_search = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            order="date",
            type="video",
            maxResults=1
        ).execute()
        
        if not video_search.get("items"):
            return {"error": "No videos found for this channel."}
            
        latest_item = video_search["items"][0]
        video_id = latest_item["id"]["videoId"]
        title = latest_item["snippet"]["title"]
        
        return {"video_id": video_id, "title": title}
    except Exception as e:
        return {"error": f"YouTube API Error: {str(e)}"}

def get_video_transcript(video_id: str) -> str:
    """
    Downloads the transcript for a given YouTube video ID.
    Returns the transcript as a single formatted string.
    """
    try:
        # Try to fetch German first, fallback to English or auto-generated
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['de', 'en'])
        
        # Format transcript
        formatted_transcript = []
        for entry in transcript_list:
            text = entry["text"].replace('\n', ' ')
            formatted_transcript.append(text)
            
        return " ".join(formatted_transcript)
    except Exception as e:
        return f"Fehler beim Abrufen des Transkripts: {str(e)}"

# Test execution blocks are avoided here to keep it clean.
