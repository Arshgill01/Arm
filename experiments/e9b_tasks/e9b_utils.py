"""Pinned document transforms copied from lm-eval v0.4.12 task definitions."""

from __future__ import annotations

import re


def _clean_hellaswag(text: str) -> str:
    text = text.strip().replace(" [title]", ". ")
    text = re.sub(r"\[.*?\]", "", text)
    return text.replace("  ", " ")


def process_hellaswag_docs(dataset):
    def process(doc):
        context = doc["ctx_a"] + " " + doc["ctx_b"].capitalize()
        return {
            "query": _clean_hellaswag(doc["activity_label"] + ": " + context),
            "choices": [_clean_hellaswag(value) for value in doc["endings"]],
            "gold": int(doc["label"]),
        }

    return dataset.map(process)


def winogrande_target(doc):
    blank = doc["sentence"].index("_") + 1
    return doc["sentence"][blank:].strip()


def winogrande_text(doc):
    return {"1": 0, "2": 1}[doc["answer"]]


def winogrande_choices(doc):
    blank = doc["sentence"].index("_")
    return [doc["sentence"][:blank] + doc["option1"], doc["sentence"][:blank] + doc["option2"]]
