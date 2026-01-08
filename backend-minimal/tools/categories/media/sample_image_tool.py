from typing import Dict, Any
from ...base.tool import BaseTool

class SampleImageTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.config = {
            "name": "showSampleImageTool",
            "description": "Display a sample image in the tool output panel",
            "shortDescription": "Showing a sample image",
            "schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }

    async def execute(self, content: Dict[str, Any] = None) -> Dict[str, Any]:
        # Model result - detailed data for the model to use
        model_result = {
            "type": "image",
            "url": "https://placekitten.com/800/400",  # Placeholder image
            "description": "A sample image of a kitten"
        }
        
        # UI result - formatted for human display
        ui_result = {
            "type": "image",
            "content": {
                "title": "Sample Image",
                "url": "https://placekitten.com/800/400",
                "description": "A sample image of a kitten"
            }
        }
        
        return self.format_response(model_result, ui_result) 