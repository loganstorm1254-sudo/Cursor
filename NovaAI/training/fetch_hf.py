"""Download Hugging Face datasets and convert them into Nova's
`<user> … <bot> … <end>` tokenized chat format.

Datasets used (small, English, good for a tiny word-level model):
  - roneneldan/TinyStories          short children's stories
  - databricks/databricks-dolly-15k instruction / Q&A
  - tatsu-lab/alpaca                instruction following (filtered)
  - allenai/sciq                    science questions
  - google/boolq                    yes/no questions with short answers
  - microsoft/wiki_qa               short factual Q&A (positive labels)

Output: hf_extra.txt  (same tokenization as make_corpus.py)
"""
from __future__ import annotations

import os
import random
import re
from collections import Counter

os.environ.setdefault("HF_DATASETS_CACHE", "/tmp/hf_cache")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from datasets import load_dataset

random.seed(7)
OUT = "hf_extra.txt"
MAX_USER_WORDS = 40
MAX_BOT_WORDS = 80
# Per-source caps so one giant set does not drown the rest
LIMITS = {
    "tinystories": 25000,
    "dolly": 12000,
    "alpaca": 15000,
    "sciq": 10000,
    "boolq": 8000,
    "wikiqa": 8000,
}


def tok(s: str) -> str:
    s = s.lower()
    s = re.sub(r"([.,!?;:'+\"()/\-])", r" \1 ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_text(s: str) -> str:
    s = s.replace("\n", " ").replace("\t", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # strip markdown-ish junk that blows up a tiny vocab
    s = re.sub(r"[*`#_\[\]{}\\|<>]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def qa_line(user: str, bot: str) -> str | None:
    u, b = tok(clean_text(user)), tok(clean_text(bot))
    if not u or not b:
        return None
    uw, bw = u.split(), b.split()
    if len(uw) > MAX_USER_WORDS or len(bw) > MAX_BOT_WORDS:
        return None
    if len(uw) < 1 or len(bw) < 2:
        return None
    # skip code-heavy / URL-heavy
    if any(x in u + " " + b for x in ("http", "www.", "{", "}", "```", "def ", "import ")):
        return None
    return f"<user> {u} <bot> {b} <end>"


def take_tinystories(n: int) -> list[str]:
    print("HF: TinyStories…")
    ds = load_dataset("roneneldan/TinyStories", split="train", streaming=True)
    out = []
    prompts = [
        "tell me a story", "tell me a short story", "story time",
        "tell me a bedtime story", "can you tell me a story",
        "tell a story", "i want a story", "another story",
    ]
    for row in ds:
        text = clean_text(row["text"])
        # keep first ~2 sentences / short paragraph
        parts = re.split(r"(?<=[.!?])\s+", text)
        story = " ".join(parts[:4]).strip()
        if len(story.split()) < 20:
            continue
        line = qa_line(random.choice(prompts), story)
        if line:
            out.append(line)
        if len(out) >= n:
            break
    print(f"  kept {len(out)}")
    return out


def take_dolly(n: int) -> list[str]:
    print("HF: databricks-dolly-15k…")
    ds = load_dataset("databricks/databricks-dolly-15k", split="train")
    out = []
    for row in ds:
        # skip long closed-QA that needs the context passage
        if row.get("category") == "closed_qa" and (row.get("context") or "").strip():
            continue
        instr = row["instruction"]
        if (row.get("context") or "").strip() and len(row["context"].split()) < 60:
            instr = f"{instr} {row['context']}"
        line = qa_line(instr, row["response"])
        if line:
            out.append(line)
        if len(out) >= n:
            break
    print(f"  kept {len(out)}")
    return out


def take_alpaca(n: int) -> list[str]:
    print("HF: alpaca…")
    ds = load_dataset("tatsu-lab/alpaca", split="train", streaming=True)
    out = []
    for row in ds:
        instr = row["instruction"]
        if (row.get("input") or "").strip():
            instr = f"{instr} {row['input']}"
        line = qa_line(instr, row["output"])
        if line:
            out.append(line)
        if len(out) >= n:
            break
    print(f"  kept {len(out)}")
    return out


def take_sciq(n: int) -> list[str]:
    print("HF: sciq…")
    ds = load_dataset("allenai/sciq", split="train")
    out = []
    for row in ds:
        q = row["question"]
        a = row["correct_answer"]
        # prefer a short sentence answer using the support snippet when short
        support = clean_text(row.get("support") or "")
        if support and len(support.split()) <= 40:
            bot = support
            if a.lower() not in bot.lower():
                bot = f"{a}. {support}"
        else:
            bot = f"the answer is {a}."
        line = qa_line(q, bot)
        if line:
            out.append(line)
        if len(out) >= n:
            break
    print(f"  kept {len(out)}")
    return out


def take_boolq(n: int) -> list[str]:
    print("HF: boolq…")
    ds = load_dataset("google/boolq", split="train")
    out = []
    for row in ds:
        q = row["question"]
        # make it a proper question if needed
        if not q.endswith("?"):
            q = q + "?"
        ans = "yes" if row["answer"] else "no"
        passage = clean_text(row.get("passage") or "")
        # short explanation from first sentence of passage
        first = re.split(r"(?<=[.!?])\s+", passage)[0] if passage else ""
        if first and len(first.split()) <= 35:
            bot = f"{ans}. {first}"
        else:
            bot = f"{ans}."
        line = qa_line(q, bot)
        if line:
            out.append(line)
        if len(out) >= n:
            break
    print(f"  kept {len(out)}")
    return out


def take_wikiqa(n: int) -> list[str]:
    print("HF: wiki_qa…")
    ds = load_dataset("microsoft/wiki_qa", split="train")
    # group positive answers per question
    by_q: dict[str, list[str]] = {}
    for row in ds:
        if int(row["label"]) != 1:
            continue
        by_q.setdefault(row["question"], []).append(row["answer"])
    out = []
    for q, answers in by_q.items():
        bot = answers[0]
        line = qa_line(q, bot)
        if line:
            out.append(line)
        if len(out) >= n:
            break
    print(f"  kept {len(out)}")
    return out


def main():
    lines: list[str] = []
    lines += take_tinystories(LIMITS["tinystories"])
    lines += take_dolly(LIMITS["dolly"])
    lines += take_alpaca(LIMITS["alpaca"])
    lines += take_sciq(LIMITS["sciq"])
    lines += take_boolq(LIMITS["boolq"])
    lines += take_wikiqa(LIMITS["wikiqa"])
    random.shuffle(lines)
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    words = Counter(w for ln in lines for w in ln.split())
    print(f"wrote {OUT}: lines={len(lines)} tokens={sum(words.values())} "
          f"unique_words={len(words)}")


if __name__ == "__main__":
    main()
