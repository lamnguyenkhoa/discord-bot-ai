"""CLI entry point for bot_act_nugger."""

import argparse
import sys
from module.bot_act_nugger.client import send_trigger_sync


def main():
    parser = argparse.ArgumentParser(
        description="Trigger the Discord bot to respond as if mentioned"
    )
    parser.add_argument("message", help="Message to send to the bot")
    parser.add_argument("--channel", required=True, help="Discord channel (e.g., #general)")
    parser.add_argument("--port", type=int, default=8765, help="Bot HTTP port (default: 8765)")

    args = parser.parse_args()

    channel = args.channel.lstrip("#")

    try:
        result = send_trigger_sync(args.message, channel, args.port)
        if result["status"] == 200:
            print(f"Trigger sent successfully to #{channel}")
            print(f"Response: {result['body']}")
        else:
            print(f"Error: {result['body'].get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        print("Is the bot running with external trigger enabled?", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
