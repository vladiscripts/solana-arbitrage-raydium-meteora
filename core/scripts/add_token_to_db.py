import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

import sys
sys.path.append('./')
from core.modules.database import add_token

async def main():
	await add_token('Bibidi', 'BCQRnuZEYw6z4AedaJRpDnQzpmqUgK8PPeLnqaNcpump')

asyncio.run(main())