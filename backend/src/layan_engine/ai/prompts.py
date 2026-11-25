"""Prompt templates for AI-assisted extraction and recovery."""
from __future__ import annotations

SYSTEM_PROMPT = (
    "You are an analytics extraction assistant for social media dashboards. "
    "You help parse metrics from DOM snippets and recover from extraction failures. "
    "Always respond with valid JSON. Never invent data — if a metric cannot be "
    "determined from the provided content, omit it. Never request or reference "
    "passwords, cookies, tokens, or authentication data."
)

EXTRACT_METRICS_PROMPT = """\
Given this DOM snippet from the {platform} analytics dashboard, extract all \
visible metrics as a JSON array.

Each item must have:
- "metric_name": a snake_case name (e.g. "page_reach", "video_views")
- "metric_value": the numeric value (parse K/M/B suffixes, percentages, etc.)
- "label": the original label text as shown on the page

DOM snippet:
```
{dom_snippet}
```

Respond ONLY with a JSON array. Example:
[{{"metric_name": "page_reach", "metric_value": 12500, "label": "Page Reach"}}]

If no metrics can be identified, respond with an empty array: []
"""

RECOVER_SELECTOR_PROMPT = """\
The CSS selector `{selector}` failed to find elements on the {platform} \
analytics dashboard. The page is at URL: {url}

Here is a simplified DOM structure of the visible page:
```
{dom_structure}
```

Suggest up to 3 alternative CSS selectors that might match the target \
element (a {target_description}). Respond ONLY with a JSON array of strings.

Example: ["div[data-testid='metric-card']", ".analytics-metric", "section.overview h3"]

If no reasonable selectors can be suggested, respond with: []
"""

CLASSIFY_CHALLENGE_PROMPT = """\
The extraction encountered an unexpected page state on {platform}. \
The page URL is: {url}

Page title: {title}
Visible text excerpt (first 500 chars):
```
{text_excerpt}
```

Classify this page as one of:
- "login_required": user needs to log in
- "challenge": CAPTCHA or security verification
- "rate_limited": too many requests
- "page_changed": dashboard layout changed
- "network_error": page failed to load
- "normal": page looks fine, extraction should retry

Respond with a JSON object: {{"classification": "...", "confidence": 0.0-1.0, "suggestion": "..."}}
"""

INTERPRET_VALUE_PROMPT = """\
Parse this analytics metric value from the {platform} dashboard:

Label: "{label}"
Raw value text: "{raw_value}"

Convert to a numeric value. Handle:
- K/M/B suffixes (e.g. "12.5K" = 12500)
- Percentages (e.g. "45.2%" = 45.2)
- Time formats (e.g. "2:34:56" in hours:min:sec)
- Comma separators, unicode minus, +/- signs

Respond with a JSON object: {{"value": <number or null>, "unit": "count"|"percent"|"seconds"|"ratio"}}
"""
