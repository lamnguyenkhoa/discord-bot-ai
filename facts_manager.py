import asyncio
import logging
import os
import re
import config

logger = logging.getLogger(__name__)

FACTS_FILE = os.path.join(config.MEMORY_DIR, "facts.md")

_USER_SECTION = "## User Facts"
_SERVER_SECTION = "## Server Facts"

_TEMPLATE = """\
# Bot Memory

## User Facts

## Server Facts
"""

_facts_lock = asyncio.Lock()

STOP_WORDS = {
    "likes", "plays", "is", "are", "was", "were", "has", "have", "had",
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "about", "from", "by", "not", "no", "i", "my", "me",
    "he", "she", "they", "we", "it",
}

_USER_FACT_RE = re.compile(r"^- \*\*(.+?)\*\*: (.+?)(?:\s+<!-- msg:(\d+) -->)?$")
_SERVER_FACT_RE = re.compile(r"^- (.+?)(?:\s+<!-- msg:(\d+) -->)?$")


def _ensure_file() -> None:
    os.makedirs(config.MEMORY_DIR, exist_ok=True)
    if not os.path.exists(FACTS_FILE):
        with open(FACTS_FILE, "w", encoding="utf-8") as f:
            f.write(_TEMPLATE)


def load_facts() -> str:
    _ensure_file()
    try:
        with open(FACTS_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error reading facts file: {e}")
        return ""


def _tokenize(text: str) -> set:
    tokens = re.split(r"\s+", text.lower())
    result = set()
    for token in tokens:
        token = token.strip(".,!?;:'\"()[]{}")
        if token and token not in STOP_WORDS:
            result.add(token)
    return result


def _parse_facts() -> list:
    _ensure_file()
    facts = []
    try:
        with open(FACTS_FILE, "r", encoding="utf-8") as f:
            current_section = None
            for line in f:
                stripped = line.rstrip("\n").strip()
                if stripped == _USER_SECTION:
                    current_section = "user"
                    continue
                elif stripped == _SERVER_SECTION:
                    current_section = "server"
                    continue

                if current_section == "user":
                    m = _USER_FACT_RE.match(stripped)
                    if m:
                        facts.append({
                            "section": "user",
                            "user": m.group(1),
                            "text": m.group(2).strip(),
                            "msg_id": int(m.group(3)) if m.group(3) else None,
                        })
                elif current_section == "server":
                    m = _SERVER_FACT_RE.match(stripped)
                    if m:
                        facts.append({
                            "section": "server",
                            "user": None,
                            "text": m.group(1).strip(),
                            "msg_id": int(m.group(2)) if m.group(2) else None,
                        })
    except Exception as e:
        logger.error(f"Error parsing facts file: {e}")
    return facts


def _write_facts(facts: list) -> None:
    user_facts = [f for f in facts if f["section"] == "user"]
    server_facts = [f for f in facts if f["section"] == "server"]

    lines = ["# Bot Memory", "", "## User Facts"]
    for f in user_facts:
        bullet = f"- **{f['user']}**: {f['text']}"
        if f.get("msg_id") is not None:
            bullet += f" <!-- msg:{f['msg_id']} -->"
        lines.append(bullet)

    lines.extend(["", "## Server Facts"])
    for f in server_facts:
        bullet = f"- {f['text']}"
        if f.get("msg_id") is not None:
            bullet += f" <!-- msg:{f['msg_id']} -->"
        lines.append(bullet)

    lines.append("")
    try:
        with open(FACTS_FILE, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except Exception as e:
        logger.error(f"Error writing facts file: {e}")


async def upsert_user_fact(user_name: str, new_fact: str, msg_id=None, old_fact=None) -> None:
    async with _facts_lock:
        facts = _parse_facts()
        user_facts = [f for f in facts if f["section"] == "user" and f["user"] == user_name]
        replaced = False

        # Correction path: exact substring match on old_fact
        if old_fact:
            for f in user_facts:
                if old_fact in f["text"] or f["text"] in old_fact:
                    idx = facts.index(f)
                    logger.info(f"Corrected fact for {user_name}: '{facts[idx]['text']}' -> '{new_fact}'")
                    facts[idx]["text"] = new_fact
                    facts[idx]["msg_id"] = msg_id
                    replaced = True
                    break

        # Keyword overlap path (>= 2 shared non-stop tokens)
        if not replaced:
            new_tokens = _tokenize(new_fact)
            best_match = None
            best_score = 0
            for f in user_facts:
                overlap = len(new_tokens & _tokenize(f["text"]))
                if overlap >= 2 and overlap > best_score:
                    best_score = overlap
                    best_match = f
            if best_match:
                idx = facts.index(best_match)
                logger.info(f"Replaced fact for {user_name}: '{facts[idx]['text']}' -> '{new_fact}' (overlap={best_score})")
                facts[idx]["text"] = new_fact
                facts[idx]["msg_id"] = msg_id
                replaced = True

        if not replaced:
            logger.info(f"Appended new fact for {user_name}: '{new_fact}'")
            facts.append({"section": "user", "user": user_name, "text": new_fact, "msg_id": msg_id})

        _write_facts(facts)


async def upsert_server_fact(new_fact: str, msg_id=None) -> None:
    async with _facts_lock:
        facts = _parse_facts()
        server_facts = [f for f in facts if f["section"] == "server"]
        new_tokens = _tokenize(new_fact)
        best_match = None
        best_score = 0

        for f in server_facts:
            overlap = len(new_tokens & _tokenize(f["text"]))
            if overlap >= 2 and overlap > best_score:
                best_score = overlap
                best_match = f

        if best_match:
            idx = facts.index(best_match)
            logger.info(f"Replaced server fact: '{facts[idx]['text']}' -> '{new_fact}' (overlap={best_score})")
            facts[idx]["text"] = new_fact
            facts[idx]["msg_id"] = msg_id
        else:
            logger.info(f"Appended new server fact: '{new_fact}'")
            facts.append({"section": "server", "user": None, "text": new_fact, "msg_id": msg_id})

        _write_facts(facts)


async def remove_facts_by_msg_id(msg_id: int) -> int:
    async with _facts_lock:
        facts = _parse_facts()
        to_keep = [f for f in facts if f.get("msg_id") != msg_id]
        removed = len(facts) - len(to_keep)
        if removed > 0:
            _write_facts(to_keep)
            logger.info(f"Removed {removed} fact(s) tagged with msg_id={msg_id}")
        else:
            logger.info(f"No facts matched msg_id={msg_id}")
        return removed
