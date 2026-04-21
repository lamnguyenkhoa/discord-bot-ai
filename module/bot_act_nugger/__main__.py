"""CLI entry point for bot_act_nugger."""

import argparse
import sys
from module.bot_act_nugger.client import send_trigger_sync


def main():
    parser = argparse.ArgumentParser(
        description="Trigger the Discord bot to respond as if mentioned"
    )
    parser.add_argument("--channel", required=True, help="Discord channel (e.g., #general)")
    parser.add_argument("--prompt", help="Prompt for bot to say something (nuggets it)")
    parser.add_argument("--message", help="Message for bot to respond to")
    parser.add_argument("--port", type=int, default=8765, help="Bot HTTP port (default: 8765)")
    parser.add_argument("--mention", help="User to mention (e.g., @username)")

    args = parser.parse_args()

    if not args.prompt and not args.message:
        print("Error: either --prompt or --message is required", file=sys.stderr)
        sys.exit(1)

    channel = args.channel.lstrip("#")
    mention = args.mention

    try:
        result = send_trigger_sync(channel, args.prompt, args.message, args.port, mention)
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