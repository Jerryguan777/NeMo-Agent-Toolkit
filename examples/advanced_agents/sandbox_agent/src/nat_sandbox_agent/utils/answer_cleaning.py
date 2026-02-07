# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Answer cleaning utilities for GAIA-style evaluation."""

import logging
import re

from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage

logger = logging.getLogger(__name__)

_ANSWER_CLEANING_PROMPT = """\
You are an answer-formatting assistant for a benchmark evaluation.

You will receive a QUESTION and a RAW ANSWER produced by an AI agent.
Your job is to extract and format ONLY the final answer so it can be \
compared to a ground-truth string.

## Rules (follow strictly)

1. **Extract only the answer** — remove any preamble ("The answer is…", \
"Based on my analysis…", "Therefore…") and any trailing explanation.
2. **Never change the substance** — do not add, remove, or alter any factual \
content. If the raw answer says "42", output "42", not "forty-two".
3. **Preserve the answer completely** — if the answer is a formula like \
"(¬A → B) ↔ (A ∨ ¬B)", output it in full. Do NOT truncate.
4. **Format according to the question**:
   - If the question asks for a number: output just the number, \
no units unless the question requires them.
   - If the question asks for "how many thousand/million X": output the \
coefficient (17000 hours → "17" for "how many thousand hours").
   - If the question asks for a name: output just the name.
   - If the question asks for a list: use the delimiter the question specifies \
(default: comma-separated).
   - If the question asks for a "setting" or "location": extract only the \
place name, not scene-heading formatting (e.g., "THE CASTLE" not \
"INT. THE CASTLE - DAY").
   - If the question asks for a "complete title": include subtitles after \
colons.
   - If the question asks for a sentence: use standard sentence formatting \
(capitalize first word, end with period).
   - Yes/No: use Title Case ("Yes" / "No").
   - Directions: use Title Case ("Left", "Right", "North", etc.).
5. **Punctuation rules**:
   - Do NOT add a trailing period unless the question explicitly asks for \
a complete sentence.
   - If the raw answer has a trailing period but the question asks for a word, \
name, or number, remove the period.
   - Never use ALL CAPS unless the source content is in ALL CAPS. Use standard \
sentence case for sentences (capitalize first word only).
6. **If the raw answer is empty or says it cannot answer**, output it as-is.
7. **Output ONLY the cleaned answer** — no quotes, no explanation, nothing else.
"""


async def clean_answer_with_llm(
    llm,
    question: str,
    response: str,
) -> str:
    """Clean the agent response using an LLM for context-aware formatting.

    The LLM sees both the original question and the raw answer, so it can
    make context-appropriate formatting decisions (e.g., keeping logical
    formulas intact, extracting setting names from scene headings).

    Falls back to returning the raw response (stripped) if the LLM call fails.

    Args:
        llm: A LangChain BaseChatModel instance.
        question: The original question that was asked.
        response: The raw agent response to clean.

    Returns:
        Cleaned answer string.
    """
    if not response or not response.strip():
        return response

    raw = response.strip()

    # Short-circuit: if the answer is already very short and simple, skip LLM
    if len(raw) <= 3 and re.fullmatch(r"-?\d+\.?\d*", raw):
        return raw

    try:
        messages = [
            SystemMessage(content=_ANSWER_CLEANING_PROMPT),
            HumanMessage(content=f"QUESTION:\n{question}\n\nRAW ANSWER:\n{raw}"),
        ]
        result = await llm.ainvoke(messages)
        cleaned = result.content.strip()

        # Guard: if the LLM returned something empty or much longer than
        # the raw answer, something went wrong — fall back to raw.
        if not cleaned:
            logger.warning("LLM answer cleaning returned empty, using raw answer")
            return raw
        if len(cleaned) > len(raw) * 2 + 50:
            logger.warning("LLM answer cleaning returned suspiciously long output, using raw answer")
            return raw

        logger.debug(f"LLM answer cleaning: {raw!r} -> {cleaned!r}")
        return cleaned

    except Exception as e:
        logger.warning(f"LLM answer cleaning failed ({e}), using raw answer")
        return raw
