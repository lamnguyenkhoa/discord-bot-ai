# Plan: Fix system_prompt.txt

**Date:** 2026-04-01
**File:** `/home/lam/claude_project/discord-bot-ai/system_prompt.txt`
**Complexity:** LOW
**Approach:** Option A -- In-place cleanup (minimal diff)

---

## Context

`system_prompt.txt` is the personality/instruction prompt for a Discord bot called Mal. It has three bugs:

1. Contradictory pronoun definitions: `"t"` defined as both "I/me" and "ta"; `"m"` defined as both "you" and "mi". These appear in the Pronouns subsection AND are repeated in the Common words subsection.
2. Accented Vietnamese in the shortcuts section: explanations use diacritics (roi, vay, duoc, nguoi, nhu the nao, truoc, nhe, thoi, di, oi, etc.) which primes the model to output accented text, directly contradicting the no-accent rule.
3. One entry uses an accented character in the shortcut itself: `"a" or "a"` (line 45) includes the accented form.

## Work Objectives

Produce a clean rewrite that fixes all three bugs while preserving every personality, tone, behavior, and hard-limit instruction exactly as-is.

## Guardrails

**Must have:**
- Zero accent marks or diacritics anywhere in the file
- Each shortcut letter/abbreviation has exactly one clear definition
- All personality, tone, behavior, response style, and hard limits sections unchanged
- File remains plain text, same filename

**Must NOT have:**
- New features, new shortcuts, or new personality traits
- Structural reorganization beyond what is needed to fix duplicates
- English-only explanations where the original mixed Vietnamese context (keep the style, just strip accents)

---

## Task Flow

### Step 1: Fix Pronouns & address subsection
Remove the duplicate inline definitions. Keep each shortcut once with a clear English meaning.

**Current (line 22):**
```
- "t" = I/me (informal), "m" = you (informal), "mk" = minh, "bn" = ban, "m" = mi, "t" = ta
```

**Target:**
```
- "t" = I/me (informal), "m" = you (informal), "mk" = minh (myself), "bn" = ban (you/friend)
```

**Acceptance criteria:** No letter appears more than once as a shortcut key in this subsection. No accented Vietnamese.

### Step 2: Fix Common words subsection
Remove the duplicate `"t" = ta` and `"m" = mi` entries (lines 26-27) since these are already covered in Pronouns. Strip all accent marks from the Vietnamese words in parenthetical explanations.

**Changes:**
- Delete `"t" = ta (me/I/I'm)` line
- Delete `"m" = mi (you)` line
- `roi` not `rồi`, `gi` not `gì`, `vay` not `vậy`, `duoc` not `được`, `cung` not `cũng`, `nguoi` not `người`, `gio` not `giờ`, `bao gio` not `bao giờ`, `nhu the nao` not `như thế nào`, `truoc` not `trước`, `viec` not `việc`, `lam` not `làm`

**Acceptance criteria:** No duplicate shortcut definitions remain. Zero accent marks in this subsection.

### Step 3: Fix Sentence endings & fillers subsection
Strip all accent marks from explanations. Remove the accented `a` character from line 45.

**Changes:**
- `nhe` not `nhé`, `thoi` not `thôi`, `di` not `đi`, `oi` not `ơi`
- Line 45: change `"a" or "ạ" (without accent: "a")` to just `"a" = polite particle`

**Acceptance criteria:** Zero accent marks in this subsection.

### Step 4: Verify the entire file
Scan the complete file for any remaining accent marks or diacritics. The only non-ASCII characters allowed are the em dash (--) used in the personality section.

**Acceptance criteria:** A grep for Vietnamese diacritics returns zero matches. All sections outside the shortcuts area are unchanged.

---

## Success Criteria

1. `grep -P '[\x{0300}-\x{036F}\x{0100}-\x{024F}\x{1EA0}-\x{1EFF}]' system_prompt.txt` returns nothing
2. Each shortcut letter/abbreviation is defined exactly once across the entire shortcuts section
3. Personality, Language & Tone (except the accented examples in the no-accent rule which are intentional), Response Style, Behavior Rules, and Hard Limits sections are byte-identical to the original
4. File is valid UTF-8 plain text

---

## ADR

- **Decision:** Option A -- in-place cleanup, minimal diff
- **Drivers:** Self-consistency of the no-accent rule; clear shortcut definitions; minimal risk of unintended changes
- **Alternatives considered:** Option B (restructure shortcuts into single flat list) -- rejected because the structural separation is fine once duplicates are removed, and a larger diff increases review burden with no functional benefit
- **Why chosen:** Smallest possible change that fixes all three bugs
- **Consequences:** The Pronouns and Common words subsections remain separate, which is a minor style preference, not a bug
- **Follow-ups:** None required
