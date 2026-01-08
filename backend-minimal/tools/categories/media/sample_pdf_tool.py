from typing import Dict, Any
from ...base.tool import BaseTool

class SamplePdfTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.config = {
            "name": "showSamplePdfTool",
            "description": "Display a sample PDF document in the tool output panel",
            "shortDescription": "Showing a sample PDF",
            "schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }

    async def execute(self, content: Dict[str, Any] = None) -> Dict[str, Any]:
        # Using a reliable sample PDF URL
        pdf_url = "https://www.adobe.com/support/products/enterprise/knowledgecenter/media/c4611_sample_explain.pdf"
        
        # Model result - detailed data for the model to use
        model_result = {
            "type": "text",
            "text": "Showing sample PDF in the left pane"
        }
        
        # UI result - formatted for human display
        ui_result = {
            "type": "pdf",
            "content": {
                "title": "Sample PDF Document",
                "url": pdf_url,
                "description": "This is a sample PDF document showing various PDF features."
            }
        }
        
        return self.format_response(model_result, ui_result) 