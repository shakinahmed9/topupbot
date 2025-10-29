
import asyncio
from discord_bot import main
from keep_alive import keep_alive

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
