---
name: Translation
content_type: translation
target_signals: [dm_share, copy_link, dwell_time, like]
content_category_default: "cross-group"
description: "Simplify complex technical ideas into clear mental models people save and share."
structural_rules:
  - "Open with: Here's how [complex topic] actually works (simplified):"
  - "Blank line"
  - "Numbered breakdown (3-5 points)"
  - "Blank line"
  - "Meta-insight connecting the points"
  - "Blank line"
  - "Bookmark CTA"
signal_strategy: "Structured simplification increases dwell time and shareability; explicit bookmark cue increases saves."
max_length: 280
is_thread_eligible: false
---

## Example Posts

### Example 1
Here's how agent memory actually works (simplified):

1. Capture only useful events.
2. Store with context, not raw noise.
3. Retrieve by task relevance.

Memory is less about storage and more about selective recall.

Bookmark this if useful.

### Example 2
Here's a fast way to evaluate new agent tools:

1. Coverage
2. Overlap
3. Cost
4. Reliability

If any score is weak, don't ship it.

Your agent needs fewer tools than you think.

### Example 3
Retries are not reliability.

Reliability = retries + bounded timeouts + safe fallback output.

If one is missing, users feel the failure.

Bookmark for your next production check.
