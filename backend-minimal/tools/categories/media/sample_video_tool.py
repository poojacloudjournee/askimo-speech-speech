from typing import Dict, Any
from ...base.tool import BaseTool

class SampleVideoTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.config = {
            "name": "showSampleVideoTool",
            "description": "Display a YouTube video in the tool output panel. Use this tool when you need to show a video demonstration, tutorial, or any YouTube content. The tool will embed the video directly in the conversation.",
            "shortDescription": "Show a YouTube video",
            "schema": {
                "type": "object",
                "properties": {
                    "videoId": {
                        "type": "string",
                        "description": "Optional: YouTube video ID to display. If not provided, will show a default video.",
                        "pattern": "^[A-Za-z0-9_-]{11}$"
                    },
                    "showControls": {
                        "type": "boolean",
                        "description": "Optional: Whether to show video controls. Defaults to true."
                    }
                }
            }
        }

    async def execute(self, content: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            # Get video ID from content or use default
            video_id = content.get("videoId", "a9__D53WsUs")
            show_controls = content.get("showControls", True)
            
            # Build embed URL with appropriate parameters
            embed_url = f"https://www.youtube-nocookie.com/embed/{video_id}?rel=0&modestbranding=1"
            if not show_controls:
                embed_url += "&controls=0"
            
            # Model result - detailed data for the model to use
            model_result = {
                "type": "video",
                "videoId": video_id,
                "url": embed_url,
                "showControls": show_controls
            }
            
            # UI result - formatted for human display
            ui_result = {
                "type": "video",
                "content": {
                    "title": "YouTube Video",
                    "url": embed_url,
                    "description": "Embedded YouTube video player"
                }
            }
            
            return self.format_response(model_result, ui_result)
            
        except Exception as e:
            error_message = f"Failed to load video: {str(e)}"
            return self.format_response(
                {"error": error_message},
                {
                    "type": "text",
                    "content": {
                        "title": "Error",
                        "message": error_message
                    }
                }
            ) 