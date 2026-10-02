"""
On-demand depth for one real occupation on Career Graph:

  - "Where this work happens": the kinds of places people in this
    occupation work, with a few well-known real examples (Indian ones
    included where the model is sure of them). Shown in the panel
    only, never as nodes.
  - "Ways people specialise": established specialisations within the
    occupation (dance styles, branches of law, instruments). Shown as
    hollow example nodes on dashed lines, clearly labelled as
    examples.

Both come from one LLM call per occupation, cached forever by SOC
code (the answer doesn't depend on the student), so the cost is paid
once per occupation across all users.

What the AI may NOT do here is add occupations. Every career node on
the graph comes from the O*NET dataset; a specialisation is a way of
working inside one of those, not a new job. The prompt forbids new,
emerging or speculative roles, and everything is validated in code
before it is cached - a response that doesn't fit is dropped rather
than repaired.
"""

import json
import re

from call_llm import call_llm

DEPTH_TEMPERATURE = 0.2

MIN_ITEMS = 2
MAX_SPECIALISATIONS = 6
MAX_WORKPLACES = 5
MAX_EXAMPLES_PER_WORKPLACE = 2
MAX_NAME_LENGTH = 40
MAX_ABOUT_LENGTH = 220
MAX_SETTING_LENGTH = 80
MAX_EXAMPLE_LENGTH = 60

SYSTEM_PROMPT = """You help a high-school student understand one real occupation in more depth. \
You are given the occupation's official title, description and sample tasks.

Respond with ONLY a JSON object, no other text, no markdown:

{"workplaces": [{"setting": "...", "examples": ["...", "..."]}],
 "specialisations": [{"name": "...", "about": "..."}]}

"workplaces" - 3 to 5 kinds of places where people in this occupation actually work.
- "setting" is a plain type of workplace, a few words (e.g. "Dance companies and troupes", "Hospitals").
- "examples" is 0 to 2 real, well-known organisations of that kind. Include Indian examples when you are \
certain one exists and really does this work. If you are not certain an organisation exists and employs \
people in this occupation, give an empty list for that setting. Never invent a name, and never guess.

"specialisations" - 3 to 6 established ways people specialise within this occupation: a style, branch, \
instrument, subject, or type of client or setting that people in this occupation have worked in for many years.
- "name" is 1 to 4 words (e.g. "Ballet", "Criminal law", "Paediatric nursing").
- "about" is one plain sentence a high-school student can follow, saying what that specialisation involves.
- These are specialisations WITHIN the given occupation - not different occupations, and not job titles.
- Never include new, emerging, speculative or futuristic roles, and never invent a specialisation. \
If the occupation has no well-established specialisations, give an empty list.

No statistics, salaries, rankings or percentages anywhere."""


def _clean(text, max_length: int) -> str:
    if not isinstance(text, str):
        return ""
    # Typographic hyphens and dashes the model likes to emit: plain
    # hyphens for the former, and no em/en dashes at all (same rule
    # main.py's strip_em_dashes applies to chat replies).
    text = text.replace("\u2010", "-").replace("\u2011", "-")
    text = re.sub("\\s*[\u2013\u2014]\\s*", ", ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if 0 < len(text) <= max_length else ""


def validate_depth(data, occupation_title: str) -> dict | None:
    """
    The cleaned {"workplaces", "specialisations"} payload, or None if
    the response isn't usable at all. Individual malformed entries are
    dropped; nothing is rewritten.
    """
    if not isinstance(data, dict):
        return None

    workplaces = []
    for item in data.get("workplaces") or []:
        if not isinstance(item, dict):
            continue
        setting = _clean(item.get("setting"), MAX_SETTING_LENGTH)
        if not setting:
            continue
        examples = [_clean(e, MAX_EXAMPLE_LENGTH) for e in (item.get("examples") or []) if isinstance(e, str)]
        workplaces.append({
            "setting": setting,
            "examples": [e for e in examples if e][:MAX_EXAMPLES_PER_WORKPLACE],
        })
    workplaces = workplaces[:MAX_WORKPLACES]

    specialisations, seen = [], set()
    for item in data.get("specialisations") or []:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"), MAX_NAME_LENGTH)
        about = _clean(item.get("about"), MAX_ABOUT_LENGTH)
        if not name or not about or len(name.split()) > 4:
            continue
        key = name.lower()
        # The occupation itself isn't a specialisation of itself.
        if key in seen or key == occupation_title.strip().lower():
            continue
        seen.add(key)
        specialisations.append({"name": name, "about": about})
    specialisations = specialisations[:MAX_SPECIALISATIONS]

    if len(workplaces) < MIN_ITEMS:
        return None
    return {"workplaces": workplaces, "specialisations": specialisations}


def generate_career_depth(occupation_title: str, occupation_description: str, tasks: list) -> dict | None:
    """Real LLM call + validation. None when both attempts fail, so
    the caller shows nothing and caches nothing."""
    task_block = "\n".join(f"- {t}" for t in tasks[:5])
    user_message = (
        f"Occupation: {occupation_title}\n"
        f"Description: {occupation_description}\n"
        f"Sample tasks:\n{task_block}\n\n"
        "Write the JSON now."
    )

    for attempt in range(2):
        try:
            raw = call_llm(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=SYSTEM_PROMPT,
                temperature=DEPTH_TEMPERATURE,
            )
            depth = validate_depth(json.loads(raw), occupation_title)
            if depth is not None:
                return depth
        except Exception:
            pass
        user_message += "\n\n(Your last answer wasn't valid JSON in the required shape. Try again, JSON only.)"

    return None
