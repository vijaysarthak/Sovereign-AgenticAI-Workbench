"""Real LLM agent adapter: local Ollama ONLY.

COMPLIANCE: document/question content must never leave this machine. There is
NO cloud fallback (no NVIDIA NIM, no Groq) anywhere in this module, by design
-- not merely deprioritized. Do not reintroduce a cloud HTTP call here without
an explicit, deliberate decision to do so; this file previously called
NVIDIA NIM and Groq as fallbacks, which sent real document passage text to
third-party cloud APIs, before that was identified as a compliance violation
and removed.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. The Agent Protocol takes NO principal, NO grade, and NO compartments.
   An agent never learns who is asking — it only ever receives already-gated passages.
2. Structured output: The model returns citations as structured JSON, NEVER scraped
   or parsed from prose.
3. Every citation must be an exact verbatim substring copied directly from a passage.
4. If citation verification fails in the runner, the failure reason is fed back
   into the next draft attempt prompt.
5. Every model call in this file goes to the local Ollama server only.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import time
from typing import Optional, Sequence
import httpx
from contracts import Citation, CodeAnswer, Draft, Passage


class RealLlmAgent:
    """Real LLM Agent: local Ollama only (air-gapped, no cloud calls)."""

    def __init__(
        self,
        ollama_api_base: Optional[str] = None,
        ollama_model: Optional[str] = None,
        ollama_fallback_model: Optional[str] = None,
    ):
        self.ollama_api_base = (ollama_api_base or os.getenv("OLLAMA_API_BASE", "http://localhost:11434")).rstrip("/")
        self.ollama_model = ollama_model or os.getenv("OLLAMA_MODEL", "granite4.1:3b")
        self.ollama_vision_model = os.getenv("OLLAMA_VISION_MODEL", "granite3.2-vision")
        # A distinct locally-installed model for the "code" intent category.
        # Model auto-selection: the intent router (classify_intent below)
        # picks this model for coding requests and the general drafting
        # model above for document questions -- a real task-based model
        # switch, still entirely local. Set to "" to fall back to
        # self.ollama_model for code too.
        self.ollama_code_model = os.getenv("OLLAMA_CODE_MODEL", "qwen2.5-coder:7b")
        # A second locally-installed text model tried, still fully locally,
        # only if the primary model produces zero citations. Different model
        # weights fail differently, so this is real added resilience without
        # any data leaving the machine. Set to "" to disable.
        # NOTE: llama3.2:latest was tried as primary and ruled out -- it hangs
        # (>120s, no response) on this app's real system+user prompt size with
        # format=json, even though it answers trivial prompts in under a
        # second. Kept only as a last-resort fallback, not primary.
        self.ollama_fallback_model = (
            ollama_fallback_model
            if ollama_fallback_model is not None
            else os.getenv("OLLAMA_FALLBACK_MODEL", "llama3.2:latest")
        )
        # Set once Ollama fails within this agent's lifetime (one HTTP request's
        # worth of retries). Without this, a struggling/overloaded Ollama burns
        # its full timeout on EVERY retry attempt — e.g. 5 retries x 60s = up to
        # 5 minutes before the request ever responds. After the first failure we
        # know it's not going to suddenly recover mid-request, so skip it.
        self._ollama_unavailable = False
        # Only try to auto-launch the Ollama app once per request (this agent's
        # lifetime), regardless of how many retries hit Ollama.
        self._ollama_launch_attempted = False
        # Set after any call that actually got a response from a local model
        # (draft/draft_code/analyze_image/draft_capability_answer) -- lets
        # callers (harness/runner.py) report which model really produced a
        # given answer, including a promoted fallback, for display in the UI.
        self.last_model_used: Optional[str] = None
        # Set only when intent classification actually got a model response;
        # stays None when it failed open to "content" without one.
        self.last_intent_model: Optional[str] = None
        self.last_intent_fallback = False

    def classify_intent(self, question: str, recent_context: str = "") -> str:
        """Route a message BEFORE retrieval into one of three categories:

        - "content": a genuine request for information that lives in the
          document corpus. Proceed to retrieval + citation-grounded drafting
          as normal.
        - "capability": a meta-question about the ASSISTANT/SYSTEM itself
          (e.g. "what can you do for me", "what files do you have access to").
          These have no grounding passage anywhere -- no document describes
          the assistant's own capabilities -- so forcing them through RAG
          either abstains with a useless "no match" or, worse, invites the
          model to invent citations for something no document actually says.
          Answered separately with real, non-hallucinated data (see runner.py).
        - "other": greeting, small talk, filler, or test input with no real
          information need of any kind. Abstain with a plain, honest message.

        Lexical retrieval scores term overlap, not intent -- it can't make
        any of these three distinctions on its own. This needs an actual
        judgment call, which only a model can make.

        Fails OPEN (returns "content") on any classification failure or
        unrecognized output: blocking a genuine question is worse than
        answering an edge case, and retrieval's own relevance scoring remains
        the safety net for truly irrelevant input that slips through.
        """
        system_prompt = (
            "You classify a single user message for a corporate document search assistant. "
            "Respond STRICTLY in valid JSON: {\"category\": \"...\"} using exactly one of these "
            "four values:\n"
            "- \"code\": an explicit request to write, generate, run, debug, or execute a piece "
            "of code, a script, a calculation done via code, or a small program -- e.g. \"write a "
            "python script that...\", \"calculate X using code\", \"run a program to...\". This is "
            "NEVER a question about document content, procedures, or the assistant's own "
            "capabilities. This ALSO includes any request that names a programming language "
            "(java, python, c, c++, javascript, etc.) together with a task to perform in it -- "
            "e.g. \"print hello world in java\", \"bubble sort in java\", \"fizzbuzz in c++\" -- "
            "even with no explicit verb like \"write\" or \"generate\": naming a programming "
            "language IS itself the signal, since no document in this corpus contains source code "
            "in any language.\n"
            "- \"content\": a genuine request for information that could be answered FROM A "
            "DOCUMENT -- even if short, informally phrased, or mixed in with unrelated chatter. "
            "This INCLUDES any question asking what to do, how to handle, or what the correct "
            "procedure is for a real-world situation or event (an emergency, an incident, a safety "
            "hazard, a compliance requirement, etc.) -- those are content questions about "
            "procedures, NOT questions about the assistant.\n"
            "- \"capability\": a question specifically about the ASSISTANT OR SYSTEM ITSELF -- what "
            "IT (the assistant) can do, what access or functionality IT has, or how IT works, "
            "including remarking on and asking about ITS OWN behavior just now (e.g. its speed, "
            "how it answered, why it did something). This is NEVER about what the USER should do "
            "in some real-world situation.\n"
            "- \"other\": a greeting, small talk, filler text, or test input with no real "
            "information need at all.\n\n"
            "Disambiguating examples (note the difference):\n"
            "- \"write a python script to compute the average of a list\" -> code (explicit "
            "request to generate/run code)\n"
            "- \"can you calculate 15% of 2400 using code and show the output\" -> code\n"
            "- \"print hello world in java\" -> code (names a programming language + a task, no "
            "document contains source code)\n"
            "- \"bubble sort in java\" -> code (same reasoning, even with no verb at all)\n"
            "- \"how to reverse a string in java\" -> code (\"in java\" makes this a code request, "
            "not a real-world procedure question, even though it starts like \"how to...\")\n"
            "- \"what should I do during an emergency\" -> content (asks about a real-world "
            "procedure that a document may describe)\n"
            "- \"what can you do for me\" -> capability (asks about the assistant's own functions)\n"
            "- \"what files do you have access to\" -> capability (asks about the assistant's own "
            "document access, not document content)\n"
            "- \"how do I report a gas leak\" -> content (asks about a real-world procedure)\n"
            "- \"that was fast, how did you do that\" -> capability (remarking on and asking about "
            "the assistant's own speed/behavior, not a document topic)\n"
            "- \"why did you answer that way\" -> capability (asking about the assistant's own "
            "reasoning/behavior)\n"
            "- \"ok what can I do here then ?\" -> capability (casual filler words like 'ok'/'then'/"
            "'so' wrapped around the question do NOT change its category -- strip filler mentally "
            "and classify the real question underneath: 'what can I do here' asks about the "
            "assistant's own functions, same as 'what can you do for me')\n\n"
            "Casual conversational wrapping (\"ok\", \"so\", \"then\", \"well\", trailing punctuation) "
            "is never itself a signal -- always classify based on the actual question inside it.\n\n"
            "If a RECENT CONVERSATION is given below, use it ONLY to resolve pronouns/references "
            "('that', 'it', 'there') in the CURRENT message -- never let the PREVIOUS answer's own "
            "topic or tone pull your classification of the CURRENT message. In particular: a "
            "previous answer that reads as a list of procedural/action steps does NOT make the "
            "current message a procedural question too -- 'what can I do here' after ANY previous "
            "answer, including a safety-procedure answer, is still asking about the assistant's own "
            "functions (capability), not asking for more procedure steps (content). Classify the "
            "CURRENT message's own words first; only consult RECENT CONVERSATION to fill in what a "
            "pronoun refers to.\n\n"
            "When genuinely unsure between content and one of the others, answer \"content\"."
        )
        user_prompt = f"CURRENT message to classify: {question}\n\n"
        if recent_context:
            user_prompt += (
                f"RECENT CONVERSATION (reference only, for resolving pronouns in the CURRENT "
                f"message -- do not let its topic influence your classification):\n{recent_context}\n\n"
            )
        user_prompt += "Respond in JSON with a single field 'category', classifying the CURRENT message above."

        self.last_intent_fallback = False
        raw_response = None
        if not self._ollama_unavailable:
            try:
                # 45s, not the drafting call's 60s, but long enough to cover a
                # cold model load: on CPU-only machines reloading an evicted
                # model routinely takes 15-20s, and the previous 15s timeout
                # silently failed open on the first request after a model
                # switch -- sending coding requests into document search.
                raw_response = self._call_ollama(system_prompt, user_prompt, temperature=0.0, timeout=45.0)
                self.last_intent_model = self.ollama_model
            except Exception as e:
                print(f"[RealLlmAgent] Intent classification via Ollama failed ({e}).")

        if raw_response is not None:
            try:
                clean = raw_response.strip()
                if clean.startswith("```"):
                    clean = re.sub(r"^```(?:json)?\n?", "", clean)
                    clean = re.sub(r"\n?```$", "", clean)
                parsed = json.loads(clean)
                category = str(parsed.get("category", "")).strip().lower()
                if category in ("content", "capability", "code", "other"):
                    return category
            except Exception:
                pass

        self.last_intent_fallback = True
        return self._keyword_category(question)

    # A programming language name, or an action verb followed by a coding noun.
    # Bare nouns alone ("the emergency response program", "the function of the
    # committee") are real document-question vocabulary, so they don't count.
    _CODE_REQUEST = re.compile(
        r"(?:\b(?:java|javascript|typescript|python|golang|kotlin|php|ruby)\b|c\+\+|c#)"
        r"|\b(?:write|generate|create|give me|make|implement)\b.{0,40}\b(?:program|script|code|function)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _keyword_category(cls, question: str) -> str:
        """Deterministic fallback used only when the model gave no usable
        classification. Still fails open to "content" for everything else --
        it just stops an obvious coding request ("write a java program...")
        from being searched for in refinery documents that contain no code."""
        return "code" if cls._CODE_REQUEST.search(question) else "content"

    def draft_capability_answer(self, question: str, facts: str, recent_context: str = "") -> Optional[str]:
        """Answer a meta-question about the assistant/system itself in natural
        language, using ONLY the given ground-truth facts.

        Unlike draft(), this needs no citation verification -- there's no
        document passage to quote when the question is about the assistant's
        own behavior, not document content. The caller (harness/runner.py)
        supplies `facts` (real capabilities, real document list, real reason
        this particular answer was fast) so the model has something true and
        specific to work from instead of a generic canned blurb, without any
        chance of it inventing a capability or document that doesn't exist.

        `recent_context` is accepted for interface consistency with draft()
        but deliberately NEVER placed in the prompt: tested live and found
        unsafe -- the local model would restate/extend prior turns' document
        content when it saw it here, and unlike draft() this path has NO
        citation verification to catch that. Conversation memory is safe for
        classify_intent (worst case: a misroute, which fails open into the
        citation-checked content path) and for draft() (any leaked claim
        still has to verify against real passages or gets rejected) -- not
        here, so it's intentionally not used.

        Returns None on any failure so the caller can fall back to a plain
        templated answer -- this is a natural-language polish step, not a
        verification-critical path.
        """
        system_prompt = (
            "You are SEVERANCE, a document question-answering assistant for MRPL. A user asked a "
            "question about how you work or what you can do, not about document content. Write a "
            "short (2-5 sentence), direct, honest answer to their SPECIFIC question, using ONLY "
            "the facts provided below. Do not invent any capability, mechanism, or document not "
            "listed in the facts. If the facts don't cover what they're asking, say so plainly "
            "rather than guessing. Respond STRICTLY in valid JSON: {\"answer\": \"...\"}."
        )
        user_prompt = f"FACTS:\n{facts}\n\nUser question: {question}\n\nRespond in JSON with a single field 'answer'."

        raw_response = None
        if not self._ollama_unavailable:
            try:
                raw_response = self._call_ollama(system_prompt, user_prompt)
                self.last_model_used = self.ollama_model
            except Exception as e:
                print(f"[RealLlmAgent] Capability answer via Ollama failed ({e}).")

        if raw_response is None:
            return None

        try:
            clean = raw_response.strip()
            if clean.startswith("```"):
                clean = re.sub(r"^```(?:json)?\n?", "", clean)
                clean = re.sub(r"\n?```$", "", clean)
            parsed = json.loads(clean)
            answer = parsed.get("answer")
            return str(answer) if answer else None
        except Exception:
            return None

    def draft_code(self, question: str, feedback: Optional[str] = None) -> CodeAnswer:
        """Propose a self-contained Python script for a coding request.

        Routed here by harness/code_runner.py's bounded loop, which is the
        code-execution analogue of harness/runner.py's citation-verification
        loop: this method only PROPOSES code, and never claims the code
        works -- agents/sandbox.py actually runs it, and the runner feeds
        any failure (traceback, non-zero exit, timeout) back into `feedback`
        for the next attempt, exactly like a failed citation gets fed back
        into the next drafting attempt.

        Uses self.ollama_code_model (a distinct locally-installed model) if
        configured -- this is the model auto-selection step: a coding
        request is handled by a different local model than a document
        question, chosen once by harness/runner.py's intent router and
        never learned or re-decided by the model itself.
        """
        system_prompt = (
            "You write short, self-contained Python 3 scripts that solve the user's request. "
            "Rules:\n"
            "1. The script must run standalone with `python script.py` -- no external network "
            "calls, no reading files outside its own directory, no interactive input().\n"
            "2. Only use the Python standard library. Do not assume any third-party package is "
            "installed.\n"
            "3. Print the final result(s) with print() so the output is captured.\n"
            "4. Keep it minimal and correct rather than clever.\n"
            "5. ALWAYS output Python 3, even if the user's request names a different language "
            "(Java, C, C++, JavaScript, etc.) -- the sandbox that runs this script can execute "
            "Python ONLY, nothing else. Never write Java/C/C++/JS syntax under any circumstances. "
            "Instead, write an equivalent Python script that solves the same underlying task, and "
            "say so plainly in 'explanation' (e.g. \"Written in Python -- this sandbox only runs "
            "Python; here is the same logic\").\n"
            "6. Respond STRICTLY in valid JSON with this exact schema:\n"
            "{\n"
            '  "code": "the complete Python script as a single string, with \\n for newlines",\n'
            '  "explanation": "one or two sentences on what the script does"\n'
            "}"
        )
        user_prompt = (
            f"Request: {question}\n\n"
            "Write the solution as a Python 3 script (even if another language is named above), with no "
            "input() calls -- use hardcoded example values. Respond in JSON with 'code' and 'explanation'."
        )
        if feedback:
            user_prompt += (
                f"\n\nPREVIOUS ATTEMPTS FAILED (fix ALL of these):\n{feedback}\n"
                "Fix the script so it actually runs successfully and produces correct output."
            )

        model_name = self.ollama_code_model or self.ollama_model
        try:
            raw_response = self._call_ollama(system_prompt, user_prompt, model=model_name, temperature=0.1)
            self.last_model_used = model_name
        except Exception as e:
            print(f"[RealLlmAgent] Code drafting via Ollama ({model_name}) failed ({e}).")
            raise

        clean = raw_response.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        try:
            parsed = json.loads(clean)
            code = str(parsed.get("code", "")).strip()
            explanation = str(parsed.get("explanation", "")).strip()
        except Exception:
            # Model didn't return valid JSON -- fall back to treating the
            # whole raw response as code, stripping a leading ```python fence
            # if present, so a well-intentioned but format-noncompliant reply
            # still gets a chance to run rather than being discarded outright.
            code = re.sub(r"^```(?:python)?\n?|```$", "", raw_response.strip())
            explanation = ""

        # The model often wraps the script in a markdown fence even INSIDE the
        # JSON "code" string; the sandbox would then execute the literal ```
        # characters and fail with a SyntaxError on line 1.
        code = re.sub(r"^```[\w+-]*[ \t]*\n?", "", code)
        code = re.sub(r"\n?```\s*$", "", code).strip()

        if not code:
            raise RuntimeError("Code drafting model returned no code.")

        if re.search(r"(?<![\w.])input\s*\(", code):
            # The sandbox has no stdin, so input() raises EOFError. Same
            # reasoning as the non-Python guard below: a specific correction
            # fixes this far more reliably than an EOFError traceback does.
            raise RuntimeError(
                "The script calls input(), but it runs non-interactively with no keyboard input. Rewrite it "
                "without input(): hardcode one or two example values from the request and print the results."
            )

        non_python_marker = self._detect_non_python(code)
        if non_python_marker:
            # Deterministic guard: the sandbox (agents/sandbox.py) can only
            # execute Python, but a small code-specialized model sometimes
            # ignores the system prompt's "always Python" instruction and
            # writes literal Java/C/C++/JS when the user names that language.
            # Feeding back a generic Python SyntaxError traceback from a
            # failed sandbox run rarely corrects this (observed in practice:
            # the model repeats the same non-Python code on retry). Raising
            # here instead gives code_runner.py's retry loop a specific,
            # actionable correction ("you wrote Java, not Python") on the
            # very next attempt, without spending a sandbox execution on
            # code we already know can't run.
            raise RuntimeError(
                f"The response was not Python (detected '{non_python_marker}'). You MUST rewrite "
                "the entire solution using ONLY Python 3 syntax -- `def`, `print()`, snake_case, "
                "no curly braces, no semicolons, no 'public class', no 'System.out.println', no "
                "'#include', no 'console.log'."
            )
        return CodeAnswer(code=code, explanation=explanation)

    @staticmethod
    def _detect_non_python(code: str) -> Optional[str]:
        """Cheap, deterministic substring check for the most common
        non-Python tells (Java/C/C++/JavaScript) missed by prompt
        instructions alone. Not exhaustive -- exists only to catch the
        common case fast, not to be a language detector; anything it
        misses still gets caught the normal way, by failing in the sandbox."""
        markers = [
            "public class ", "public static void main", "System.out.println",
            "#include <", "using namespace ", "console.log(", "void main(",
            "int main(", "std::", "cout <<", "cin >>",
        ]
        for marker in markers:
            if marker in code:
                return marker
        return None

    def draft(
        self,
        question: str,
        passages: Sequence[Passage],
        feedback: Optional[str] = None,
        recent_context: str = "",
    ) -> Draft:
        """Generate structured draft answer and verbatim citations from gated passages."""
        if not passages:
            return Draft(
                answer="No readable documents available to address this inquiry.",
                citations=[],
            )

        # Build prompt containing ONLY allowed passages
        passages_text = ""
        for p in passages:
            passages_text += f"\n--- Document: {p.doc_id} | Page: {p.page} ---\n{p.text}\n"

        system_prompt = (
            "You are SEVERANCE, the sovereign document intelligence synthesis agent for MRPL.\n"
            "Answer using strictly the provided readable passages.\n\n"
            "ANSWER RULES:\n"
            "1. Keep 'answer' concise: about 80-150 words, using concrete detail actually present in the\n"
            "   passages (named items, quantities, procedures, thresholds) — not restated question text.\n"
            "2. Don't repeat the same sentence pattern per item; each point should add a distinct fact.\n"
            "3. Write 'answer' as GitHub-Flavored Markdown ('##' headings, '-' bullets, '**bold**' for key terms).\n"
            "4. Only state facts the passages support. If they're thin or partial, say so briefly.\n\n"
            "CRITICAL CITATION RULES:\n"
            "5. The 'citations' array must NEVER be empty. Every answer, even a partial one, MUST include at\n"
            "   least one verbatim citation from a passage you examined. Never respond with 'citations': [].\n"
            "6. Every citation 'quote' must be an EXACT verbatim substring copied directly from the text —\n"
            "   never altered, summarized, or paraphrased.\n"
            "7. Quotes must be 20-300 characters and at least 5 words. Give ONLY 1 or 2 citations, each a\n"
            "   single short sentence or phrase (about 8-25 words) copied character-for-character from ONE\n"
            "   passage. Never join words from different sentences, lines, or pages into one quote, and never\n"
            "   reword, shorten, or fix anything inside a quote. Every citation is machine-checked and a single\n"
            "   inexact one rejects the whole answer -- fewer exact quotes are far better than more loose ones.\n"
            "8. Read the page number ONLY from the passage's own '--- Document: <doc_id> | Page: <page> ---'\n"
            "   header. Passage text often has its own numbering (clause/schedule numbers, list entries like\n"
            "   '25. Cause of leakage...') that looks like a page number but is NOT — e.g. under a header\n"
            "   'Page: 49' whose body contains '25. Cause of leakage...', the correct page is 49, never 25.\n"
            "9. Respond STRICTLY in valid JSON with this exact schema:\n"
            "{\n"
            '  "answer": "Concise, Markdown-formatted synthesis grounded in specific passage detail.",\n'
            '  "citations": [\n'
            '    {"doc_id": "document-id", "page": 1, "quote": "exact verbatim text copied from passage"}\n'
            "  ]\n"
            "}"
        )

        user_prompt = f"Available Readable Passages:\n{passages_text}\n\n"
        if recent_context:
            user_prompt += (
                f"RECENT CONVERSATION (for understanding a casual follow-up question only -- "
                f"NEVER a source for citations; every citation must still come from the Available "
                f"Readable Passages above):\n{recent_context}\n\n"
            )
        user_prompt += (
            f"User Question: {question}\n\n"
            "RESPONSE FORMAT REQUIREMENT:\n"
            "Respond STRICTLY in valid JSON with top-level keys 'answer' (a concise, ~80-150 word,\n"
            "Markdown-formatted answer built from specific details in the passages — not a repeated sentence\n"
            "template per item) and 'citations' (a list of verbatim\n"
            "quotation objects from the passages above). Do NOT output custom\n"
            "top-level keys.\n"
        )
        if feedback:
            user_prompt += (
                f"\nIMPORTANT PREVIOUS ATTEMPT FEEDBACK:\n{feedback}\n"
                "The previous citation failed verification. Make sure your quote is a literal, character-for-character "
                "verbatim copy of text in the specified document and page.\n"
            )

        # Local-only resilience strategy: for each locally-installed model in
        # sequence (primary, then a different fallback model if configured),
        # try a normal draft; if it comes back with zero citations, try one
        # narrower "citation repair" call against the SAME model before
        # moving on -- extracting a supporting verbatim quote for an already
        # -written answer is a much easier task for a small model than
        # composing the answer AND citing it in one shot, so this recovers
        # a real share of cases without ever leaving the machine. Only after
        # every local model (and its repair attempt) fails to produce a
        # citation do we give up. See module docstring: no cloud fallback.
        fallback_draft: Optional[Draft] = None
        tried_models = []
        for model_name in (self.ollama_model, self.ollama_fallback_model):
            if not model_name or model_name in tried_models:
                continue
            tried_models.append(model_name)

            if self._ollama_unavailable:
                break
            try:
                raw_response = self._call_ollama(system_prompt, user_prompt, model=model_name)
                self.last_model_used = model_name
            except Exception as e:
                if isinstance(e, httpx.TimeoutException):
                    self._ollama_unavailable = True
                print(f"[RealLlmAgent] Ollama ({model_name}) call failed ({e}).")
                continue

            draft = self._parse_draft(raw_response, passages)
            if draft.citations:
                return draft
            fallback_draft = fallback_draft or draft
            print(f"[RealLlmAgent] Ollama ({model_name}) returned zero citations. Trying citation repair.")

            repaired = self._repair_citations(model_name, draft.answer, passages)
            if repaired:
                return Draft(answer=draft.answer, citations=repaired)

        if fallback_draft is not None:
            # No local model produced a citation, but at least one responded --
            # return its draft so harness/verify.py's real "no citations were
            # provided" feedback flows into the next retry, instead of masking
            # a genuine drafting difficulty as an infrastructure failure.
            return fallback_draft

        # Do NOT return an empty Draft here: harness/verify.py would trivially
        # pass it as "verified" (nothing to check), recording this
        # infrastructure failure as a verified "answered" response. Raising
        # lets the retry loop treat it like any other failed attempt and
        # abstain honestly.
        raise RuntimeError("The local Ollama backend failed to respond.")

    def _repair_citations(
        self, model_name: str, answer: str, passages: Sequence[Passage]
    ) -> list[Citation]:
        """Narrow follow-up call: given an already-written answer, ask the
        SAME local model only to extract verbatim supporting quotes from the
        passages -- a simpler, more constrained task than composing the
        answer and citing it simultaneously, so a small model is more likely
        to get it right. Returns [] on any failure; never raises.
        """
        passages_text = ""
        for p in passages:
            passages_text += f"\n--- Document: {p.doc_id} | Page: {p.page} ---\n{p.text}\n"

        system_prompt = (
            "You are given an ANSWER and the PASSAGES it was based on. Your only job is to find "
            "1 to 3 short EXACT verbatim quotes from the passages that best support the answer. "
            "Each quote must be copied character-for-character from the passage text -- do not "
            "paraphrase, summarize, fix typos, or alter punctuation in any way. Each quote must be "
            "20-300 characters and at least 5 words. Respond STRICTLY in valid JSON:\n"
            "{\n"
            '  "citations": [\n'
            '    {"doc_id": "document-id", "page": 1, "quote": "exact verbatim text copied from passage"}\n'
            "  ]\n"
            "}"
        )
        user_prompt = (
            f"PASSAGES:\n{passages_text}\n\nANSWER:\n{answer}\n\n"
            "Respond in JSON with a single field 'citations' (a list of 1-3 verbatim quotation "
            "objects copied from the passages above)."
        )

        try:
            raw_response = self._call_ollama(system_prompt, user_prompt, model=model_name)
        except Exception as e:
            print(f"[RealLlmAgent] Citation repair via Ollama ({model_name}) failed ({e}).")
            return []

        try:
            clean = raw_response.strip()
            if clean.startswith("```"):
                clean = re.sub(r"^```(?:json)?\n?", "", clean)
                clean = re.sub(r"\n?```$", "", clean)
            parsed = json.loads(clean)
            raw_citations = parsed.get("citations", []) if isinstance(parsed, dict) else []
        except Exception:
            return []

        return self._parse_citations(raw_citations)

    def _ensure_ollama_running(self) -> None:
        """Best-effort: if the local Ollama server isn't reachable, try to launch
        the Ollama app (macOS) and give it a few seconds to come up.

        Quitting the Ollama app takes the primary backend offline until someone
        notices and manually relaunches it; this closes that gap automatically
        for the common case (Ollama.app quit, server not running). Only
        attempted once per request, and it never blocks longer than the poll
        window below -- if it can't recover in time, the caller's normal
        request just proceeds to fail this attempt (there is no cloud
        fallback in this module -- see module docstring).
        """
        if self._ollama_launch_attempted:
            return
        self._ollama_launch_attempted = True

        health_url = f"{self.ollama_api_base}/api/tags"
        try:
            with httpx.Client(timeout=2.0) as client:
                client.get(health_url)
            return  # already up
        except httpx.HTTPError:
            pass

        if platform.system() != "Darwin":
            return  # only know how to auto-launch the macOS app

        try:
            subprocess.Popen(
                ["open", "-a", "Ollama"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"[RealLlmAgent] Could not launch Ollama app ({e}).")
            return

        print("[RealLlmAgent] Ollama server unreachable -- launched the Ollama app, waiting for it to come up...")
        deadline = time.time() + 8.0
        while time.time() < deadline:
            try:
                with httpx.Client(timeout=1.5) as client:
                    client.get(health_url)
                print("[RealLlmAgent] Ollama server is back up.")
                return
            except httpx.HTTPError:
                time.sleep(1.0)
        print("[RealLlmAgent] Ollama app launched but server did not come up within 8s; proceeding to fallbacks for this request.")

    def _call_ollama(
        self, system_prompt: str, user_prompt: str, model: Optional[str] = None,
        temperature: float = 0.1, timeout: float = 60.0,
    ) -> str:
        """Call local Ollama endpoint with the given model (defaults to self.ollama_model)."""
        self._ensure_ollama_running()
        url = f"{self.ollama_api_base}/api/chat"
        payload = {
            "model": model or self.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            # num_predict caps generation length so a verbose or looping
            # response can't run out the full request timeout -- 700 tokens
            # comfortably covers an ~80-150 word answer plus a few JSON
            # citation objects, with headroom, but bounds the worst case.
            # num_ctx: Ollama's 4096-token default is too tight -- a 5-passage
            # draft prompt measured ~3000 tokens before retry feedback and
            # conversation context are appended, which would cut the JSON reply off.
            "options": {"temperature": temperature, "num_predict": 700, "num_ctx": 8192},
        }
        with httpx.Client(timeout=timeout) as client:
            res = client.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
            return data["message"]["content"]

    def analyze_image(self, question: str, image_base64: str) -> str:
        """Ask the local vision model (granite3.2-vision by default) to answer
        a question about ONE image.

        This deliberately returns plain natural-language text, NOT the
        structured {answer, citations} JSON draft() uses -- there is no
        verbatim substring of an image to verify a "citation" against, so
        harness/runner.py labels this output as an unverified visual
        observation, distinct from citation-verified text findings, rather
        than routing it through harness/verify.py at all.
        """
        self._ensure_ollama_running()
        instructed = (
            "Answer the following question about this image as accurately and specifically "
            "as possible, describing only what is actually visible. If the question doesn't "
            "apply to what's shown, say so plainly.\n\nQuestion: " + question
        )
        # Some very small vision models (observed: moondream) emit an
        # immediate stop token -- a 200 OK with empty content -- for the
        # instruction-wrapped prompt, yet answer the bare question fine. Retry
        # once with the bare question rather than silently reporting a blank
        # observation, and raise if both come back empty so the caller shows
        # an explicit "vision analysis failed" instead of nothing.
        for content in (instructed, question):
            description = self._describe_image(content, image_base64)
            if description:
                self.last_model_used = self.ollama_vision_model
                return description
        raise RuntimeError(
            f"Vision model '{self.ollama_vision_model}' returned an empty description for this image."
        )

    # Image tokens + prompt + answer must all fit in the context window. Ollama
    # otherwise runs models at its 4096-token default: a single phone photo can
    # take ~3400 tokens by itself, so generation hit that limit mid-answer and
    # the description came back cut off (observed: done_reason="length").
    VISION_NUM_CTX = 16384

    def _describe_image(self, content: str, image_base64: str) -> str:
        """One description attempt; retries once with double the context if the
        answer was cut off, and marks it explicitly if it is still incomplete."""
        text, done_reason = self._call_vision(content, image_base64, num_ctx=self.VISION_NUM_CTX)
        if done_reason != "length":
            return text
        retry_text, retry_reason = self._call_vision(content, image_base64, num_ctx=self.VISION_NUM_CTX * 2)
        if len(retry_text) >= len(text):
            text, done_reason = retry_text, retry_reason
        if done_reason == "length" and text:
            text += "\n\n_(Description incomplete: the vision model ran out of context for this image.)_"
        return text

    def _call_vision(self, content: str, image_base64: str, num_ctx: int) -> tuple[str, Optional[str]]:
        payload = {
            "model": self.ollama_vision_model,
            "messages": [{"role": "user", "content": content, "images": [image_base64]}],
            "stream": False,
            # Thinking-capable vision models (e.g. qwen3.5) otherwise spend most
            # of the token budget on hidden reasoning the user never sees.
            # Models without a thinking mode ignore this.
            "think": False,
            "options": {"temperature": 0.1, "num_ctx": num_ctx},
        }
        # Vision models take meaningfully longer than text-only calls (image
        # encoding + a bigger multimodal forward pass), hence the longer timeout.
        with httpx.Client(timeout=180.0) as client:
            res = client.post(f"{self.ollama_api_base}/api/chat", json=payload)
            if res.status_code == 400 and "think" in res.text.lower():
                # Model has no thinking mode and this Ollama rejects the flag.
                payload.pop("think")
                res = client.post(f"{self.ollama_api_base}/api/chat", json=payload)
            try:
                res.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise httpx.HTTPStatusError(
                    f"{exc}. Response body: {res.text[:500]}",
                    request=exc.request,
                    response=exc.response,
                ) from exc
            data = res.json()
            return data["message"]["content"].strip(), data.get("done_reason")

    def _parse_draft(self, raw_content: str, passages: Sequence[Passage]) -> Draft:
        """Safely parse and validate structured Draft JSON."""
        clean_content = raw_content.strip()
        # Strip markdown code blocks if present
        if clean_content.startswith("```"):
            clean_content = re.sub(r"^```(?:json)?\n?", "", clean_content)
            clean_content = re.sub(r"\n?```$", "", clean_content)

        try:
            parsed = json.loads(clean_content)
        except Exception:
            # Attempt regex extraction of JSON object
            match = re.search(r"\{.*\}", clean_content, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
            else:
                return Draft(answer=clean_content, citations=[])

        if not isinstance(parsed, dict):
            return Draft(answer=clean_content, citations=[])

        if "answer" in parsed:
            answer = str(parsed["answer"])
        else:
            # If the model returned keys like {"possible_dangers": [...]}:
            # Intelligently convert into clean, human-readable text instead of dumping raw JSON syntax
            lines = []
            for k, v in parsed.items():
                if k == "citations":
                    continue
                title = k.replace("_", " ").title()
                if isinstance(v, list):
                    lines.append(f"{title}:")
                    for item in v:
                        lines.append(f"• {str(item).replace('_', ' ').capitalize()}")
                elif isinstance(v, dict):
                    lines.append(f"{title}:")
                    for sub_k, sub_v in v.items():
                        lines.append(f"• {sub_k.replace('_', ' ').title()}: {sub_v}")
                else:
                    lines.append(f"{title}: {v}")
            answer = "\n".join(lines) if lines else clean_content
        citations = self._parse_citations(parsed.get("citations", []))
        return Draft(answer=answer, citations=citations)

    def _parse_citations(self, raw_citations) -> list[Citation]:
        """Validate a raw parsed-JSON citations list into Citation objects,
        dropping any entry that doesn't fit the expected shape."""
        citations: list[Citation] = []
        if isinstance(raw_citations, list):
            for c in raw_citations:
                if not isinstance(c, dict):
                    continue
                try:
                    doc_id = str(c.get("doc_id", "")).strip()
                    page = int(c.get("page", 1))
                    quote = str(c.get("quote", "")).strip()
                    citations.append(Citation(doc_id=doc_id, page=page, quote=quote))
                except Exception:
                    # Invalid citation dropped
                    pass
        return citations
