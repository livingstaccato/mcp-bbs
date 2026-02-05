"""Connection and session management for TW2002 Trading Bot."""

from .logging_utils import logger


async def connect(bot, host="localhost", port=2002):
    """Connect to TW2002 BBS.

    Args:
        bot: TradingBot instance
        host: BBS hostname (default: localhost)
        port: BBS port (default: 2002)
    """
    print(f"\n🔗 Connecting to {host}:{port}...")
    bot.session_id = await bot.session_manager.create_session(
        host=host, port=port, cols=80, rows=25, term="ANSI", timeout=10.0
    )
    bot.session = await bot.session_manager.get_session(bot.session_id)
    await bot.session_manager.enable_learning(
        bot.session_id, bot.knowledge_root, namespace="tw2002"
    )
    print(f"✓ Connected")
    logger.info("bbs_connected", host=host, port=port, session_id=bot.session_id)
