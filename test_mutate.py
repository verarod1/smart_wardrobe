import datetime
import asyncio
from aiogram.types import Message, Chat

async def main():
    chat = Chat(id=123, type='private')
    msg = Message(message_id=1, date=datetime.datetime.now(), chat=chat, text="Hello")
    try:
        new_msg = msg.model_copy(update={"text": "World"})
        print(f"Success! New text: {new_msg.text}")
    except Exception as e:
        print(f"Exception mutating: {type(e).__name__} - {e}")

if __name__ == "__main__":
    asyncio.run(main())
