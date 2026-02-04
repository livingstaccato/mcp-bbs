
import asyncio
from mcp_bbs.core.session_manager import SessionManager
from mcp_bbs.config import get_default_knowledge_root

async def login():
    manager = SessionManager()
    knowledge_root = get_default_knowledge_root()
    
    sid = await manager.create_session(host="localhost", port=2002, reuse=False)
    session = await manager.get_session(sid)
    
    await asyncio.sleep(2)
    await session.read(1000, 8192)
    
    print("Selecting A...")
    await session.send("A")
    await asyncio.sleep(1)
    await session.read(1000, 8192)
    
    print("Sending password 'game'...")
    await session.send("game")
    await asyncio.sleep(1)
    await session.read(1000, 8192)
    
    print("Sending CR...")
    await session.send("")
    await asyncio.sleep(1)
    snapshot = await session.read(1000, 8192)
    print(f"Screen after CR: {snapshot.get('screen')}")
    
    print("Sending name 'gemini'...")
    await session.send("gemini")
    await asyncio.sleep(1)
    await session.send("")
    await asyncio.sleep(1)
    await session.read(1000, 8192)
    
    print("Sending Y for ANSI...")
    await session.send("Y")
    await asyncio.sleep(2)
    await session.read(1000, 8192)
    
    print("Sending T to play...")
    await session.send("T")
    await asyncio.sleep(1)
    await session.send("")
    await asyncio.sleep(1)
    await session.read(1000, 8192)
    
    print("Sending N for log...")
    await session.send("N")
    await asyncio.sleep(2)
    await session.read(1000, 8192)
    
    print("Sending Y for new character...")
    await session.send("Y")
    await asyncio.sleep(1)
    await session.send("")
    await asyncio.sleep(2)
    snapshot = await session.read(1000, 8192)
    print(f"Final Screen:
{snapshot.get('screen')}")
    
    await manager.close_all_sessions()

if __name__ == "__main__":
    asyncio.run(login())
