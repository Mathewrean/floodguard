import json
from channels.generic.websocket import AsyncWebsocketConsumer

class AlertConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'alert_updates'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'message': 'Alert WebSocket connected'
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        pass

    async def alert_message(self, event):
        await self.send(text_data=json.dumps(event))


class FloodMapConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'flood_map_updates'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'message': 'Flood map WebSocket connected'
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        pass

    async def flood_update(self, event):
        await self.send(text_data=json.dumps(event))
