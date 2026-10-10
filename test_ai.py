import asyncio
import json
import os
from ai import parse_user_intent
from dotenv import load_dotenv

load_dotenv()

async def main():
    res = await parse_user_intent("Собери чемодан в Дубай с 12.10 на 14 дней, весом 17кг")
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
