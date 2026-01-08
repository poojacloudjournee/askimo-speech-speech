import datetime
import hashlib
import random
from typing import Dict, Any
from ...base.tool import BaseTool

class TrackOrderTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.config = {
            "name": "trackOrderTool",
            "description": "Track the status of an order by order ID",
            "shortDescription": "Tracking an order",
            "schema": {
                "type": "object",
                "properties": {
                    "orderId": {
                        "type": "string",
                        "description": "The order ID to track"
                    },
                    "requestNotifications": {
                        "type": "boolean",
                        "description": "Whether to request notifications for this order"
                    }
                },
                "required": ["orderId"]
            }
        }

    async def execute(self, content: Dict[str, Any]) -> Dict[str, Any]:
        order_id = content.get("orderId", "")
        request_notifications = content.get("requestNotifications", False)
        
        # Create deterministic randomness based on order ID
        seed = int(hashlib.md5(str(order_id).encode(), usedforsecurity=False).hexdigest(), 16) % 10000
        random.seed(seed)
        
        # Possible statuses with weights
        statuses = [
            "Order received", 
            "Processing", 
            "Preparing for shipment",
            "Shipped",
            "In transit", 
            "Out for delivery",
            "Delivered",
            "Delayed"
        ]
        weights = [10, 15, 15, 20, 20, 10, 5, 3]
        status = random.choices(statuses, weights=weights, k=1)[0]
        
        # Generate delivery date based on status
        today = datetime.datetime.now()
        if status == "Delivered":
            delivery_days = -random.randint(0, 3)
        elif status == "Out for delivery":
            delivery_days = 0
        else:
            delivery_days = random.randint(1, 10)
            
        estimated_delivery = (today + datetime.timedelta(days=delivery_days)).strftime("%Y-%m-%d")
        
        # Model result - detailed data for the model to use
        model_result = {
            "orderStatus": status,
            "orderNumber": order_id,
            "estimatedDelivery": estimated_delivery,
            "notificationStatus": f"You will receive notifications for order {order_id}" if request_notifications else ""
        }

        if status == "In transit":
            model_result["currentLocation"] = "Distribution Center"
        elif status == "Delivered":
            model_result["deliveryLocation"] = "Front Door"
        elif status == "Delayed":
            model_result["additionalInfo"] = "Weather delays possible"

        # UI result - formatted as a card for better presentation
        ui_result = {
            "type": "card",
            "content": {
                "title": f"Order #{order_id}",
                "description": f"Status: {status}",
                "details": {
                    "Estimated Delivery": estimated_delivery,
                    "Current Status": status
                },
                "footer": {
                    "text": model_result.get("additionalInfo", "") or 
                           model_result.get("currentLocation", "") or 
                           model_result.get("deliveryLocation", ""),
                    "action": {
                        "text": "Track Another Order",
                        "url": "#"
                    }
                }
            }
        }

        # Add notifications info if requested
        if request_notifications:
            ui_result["content"]["details"]["Notifications"] = "Enabled"
        
        return self.format_response(model_result, ui_result) 