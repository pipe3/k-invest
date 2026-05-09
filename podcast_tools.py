from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi


def get_latest_video_id(api_key: str, channel_handle: str = "@doppelgaengerio") -> dict:
    """
    Fetches the latest video ID and title for the podcast channel.
    Returns: {"video_id": "...", "title": "..."}
    """
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        
        # We hardcode the channel ID for @doppelgaengerio to avoid flaky handle searches
        # Channel ID: UCZsFRBZ-5wNeFEqLFqnemcw
        channel_id = "UCZsFRBZ-5wNeFEqLFqnemcw"
        
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

def get_recent_videos(api_key: str, n: int = 15) -> list:
    """
    Returns the n most recent videos for the podcast channel.
    Each entry: {"video_id": "...", "title": "...", "published_at": "..."}
    """
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        channel_id = "UCZsFRBZ-5wNeFEqLFqnemcw"
        result = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            order="date",
            type="video",
            maxResults=n
        ).execute()
        videos = []
        for item in result.get("items", []):
            videos.append({
                "video_id":     item["id"]["videoId"],
                "title":        item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"][:10],
            })
        return videos
    except Exception as e:
        return [{"error": f"YouTube API Error: {str(e)}"}]

def get_video_transcript(video_id: str) -> str:
    """
    Downloads the transcript for a given YouTube video ID.
    Returns the transcript as a single formatted string.
    """
    try:
        # Try standard PyPI youtube-transcript-api (0.6.x)
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['de', 'en'])
        except AttributeError:
            # Fallback to local/custom version API
            transcript_list = YouTubeTranscriptApi().fetch(video_id, languages=['de', 'en'])
        
        # Format transcript
        formatted_transcript = []
        for entry in transcript_list:
            # Handle both dictionary and object formats
            if isinstance(entry, dict):
                text = entry.get("text", "")
            else:
                text = getattr(entry, "text", "")
            
            text = text.replace('\n', ' ')
            formatted_transcript.append(text)
            
        return " ".join(formatted_transcript)
    except Exception as e:
        return f"Fehler beim Abrufen des Transkripts: {str(e)}"

# Test execution blocks are avoided here to keep it clean.
