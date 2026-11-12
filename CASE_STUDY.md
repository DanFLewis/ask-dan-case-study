# Ask Dan: a grounded, locally hosted Q&A assistant

## Problem

A personal site can answer "what has this person done" with a resume, but visitors (recruiters, hiring managers) usually have a narrower question: does he know X, what did he do at Y, would he fit this role. I wanted a chat box that answers those questions from facts I have approved, runs on hardware I already own so there is no per-token bill, and cannot be talked into saying anything else.

The constraints that shaped the design:

- It speaks for a real person, so a wrong answer is worse than "I don't know."
- It sits on a public page, so every visitor message is hostile input until proven otherwise.
- The model runs on a home GPU, so the public internet must never reach it directly, and the box can be switched off without anything breaking.

## Architecture

```
site (chat box)
  -> Cloudflare Turnstile token
  -> Cloudflare Worker      holds the gateway key, checks Turnstile and Origin, allows only POST /ask
  -> tunnel                 public hostname, forwards to the home machine
  -> gateway (Node)         POST /ask: key scope check, rate limits, session history, builds the prompt
  -> Ollama /api/chat       gemma4:e4b, think:false, num_ctx 8192, temperature 0.1, num_predict 200
```

What each layer does, as implemented:

- **Worker.** Accepts only `POST /ask` from an allowlist of site origins. Rejects bodies over 4096 bytes and questions over 500 characters, requires a Turnstile token and verifies it server-side, then forwards the question with the gateway key (a Worker secret, never in page JavaScript) and the visitor IP in a header. It trims the answer to 1200 characters and returns a generic "offline" error for any upstream failure. It is deployed and serving the site.
- **Gateway `/ask` route.** Off unless an environment flag is set. Needs a key with scope `ask`. Visitors send only `{question, session_id}`; any other field is rejected, so a caller can never supply a system prompt, a model name, or message history. Rate limits: 5 requests per minute per key by default, 8 per minute per IP. Body cap 4096 bytes, question cap 500 characters, and a bounded request queue that returns 503 when full.
- **Sessions.** Follow-up history lives on the server only, in memory: the last 4 turns, a 30 minute TTL, at most 200 sessions, and a session is bound to the IP that created it. A forged or foreign session id silently starts a fresh session.
- **Model call.** The gateway builds the message list itself: the fixed system prompt with the fact sheet substituted in, then history, then the question. It uses Ollama's native `/api/chat` rather than the OpenAI-compatible endpoint so that `think: false` and `num_ctx` are set per request.
- **Logging.** Metadata by default (time, status, latency, token counts). The design recommendation was not to log question text unless the owner opts in.
- **Failure mode.** The assistant only answers while the home machine is on and the tunnel is up. The site is meant to show "Assistant offline" with a link to the resume.

## Grounding

Small models invent plausible details. The defense is to make the allowed answer set small and explicit rather than to hope the model behaves.

1. **One source of truth.** A single fact sheet (a markdown file, about 18K characters) is the only place facts about the person live. The system prompt says to answer only from it and, when it has no answer, to reply with one exact sentence ("I don't have that information. You can ask Dan directly.").
2. **Re-read on every request.** The gateway reads the prompt and fact sheet from disk per request, so an edit to the fact sheet takes effect immediately with no restart and no stale copy.
3. **Unconfirmed claims are removed, not softened.** The first draft was built only from the resume and carried `[CONFIRM]` markers on anything the owner had not approved. The handover notes from that stage list specific figures as awaiting a yes/no (an ARR figure and a call-volume figure). The current fact sheet no longer contains them. Where a claim is only partly true, the sheet says exactly how far it goes: "Did some response caching" rather than a production caching system, and "designed, not shipped" for a memory design. A sample of the same structure is in `example/factsheet.example.md`.
4. **A "not covered" list.** The fact sheet ends with an explicit list of topics that always get the canned "I don't have that" answer: compensation, reasons for leaving jobs, job-search status, references, family, address, and so on. Refusal is the default for the questions a recruiter is most likely to push on.
5. **Prompt rules that came from failures.** The rules grew by testing: never mention the "fact sheet" in answers, never use superlatives or rank the person against others, fixed handling for "should I hire him" (strong for matching roles, "I can't confirm that fit" for excluded or unsupported ones), and a rule that follow-up words like "that" and "more" refer to the previous answer. The prompt pattern is in `example/system_prompt.example.txt`.
6. **Messages are questions, never instructions.** The prompt states that visitor text cannot change the rules, and the gateway enforces the structural half of that (no client-supplied system prompt or history).

## Evaluation

The eval is a regex-checked test set. Each case has a category, a question, `must` patterns that every answer has to match, and `mustnot` patterns it must not. Cases cover four kinds of input:

| Category | What it checks |
|---|---|
| in-scope | Known facts come back correctly, without mentioning the fact sheet |
| unknown | Missing facts get the canned refusal instead of a guess (salary, reasons for leaving, a language not on the sheet, private contact details) |
| off-topic | Code requests, trivia, jokes, translation are declined |
| injection | Prompt-leak requests, persona swaps, fake "system override", fabricated claims the user asks the bot to confirm, fake closing tags |

A second set covers multi-turn behavior, which single-turn tests miss: follow-ups that depend on the previous answer, a friendly turn followed by an off-topic or jailbreak turn, a persona attack on turn three, a false claim that the bot "agreed earlier," and a request to repeat everything above. Settings for all runs: temperature 0.1, num_predict 200, think off.

The scripts run at three levels: straight against Ollama, through the gateway `/ask` route (which adds the real prompt assembly, sessions, and rate limits), and multi-turn through the gateway. Gateway runs sleep between requests to stay under the rate limit.

Results in the result files (run against the real fact sheet, which is private; sanitized equivalents of the cases are in `tests/`):

| Run | File | Result |
|---|---|---|
| Single-turn, direct to Ollama, gemma4:e4b | `results_gemma4_e4b.json` | 50 of 50 pass (24 in-scope, 12 unknown, 10 injection, 4 off-topic) |
| Single-turn through the gateway `/ask` route | `results_via_ask.json` | 40 of 40 pass (an earlier, smaller version of the same set) |
| Multi-turn through the gateway | `results_multi_via_ask.json` | 15 of 15 pass |

The multi-turn script also runs two session checks (a real session id is stable across turns; a forged id gets a new session). Counting those, the script's total is 17 of 17. The two checks only print to the console and are not saved in a result file, so the 15 above is what the files confirm and the 17 is the script's own count.

Limits worth stating:

- The regex checks are lenient. The author also read the non-in-scope answers by hand when the first set ran and found every refusal was the exact canned line. The later runs were not re-read.
- The test set was extended while the prompt was tuned, so the pass counts show the prompt handles the known cases, not unseen ones. Paraphrase hallucination on in-scope questions needs a larger set.
- Only gemma4:e4b was run through the full suite. A second model (qwen3.5:9b) was not tested; the notes record gemma as about twice as fast.
- No latency or accuracy figures are claimed beyond the pass counts above.

## Bugs found and fixed

Verification status is stated per item, checked against the source files.

**1. History dropped on every request (token estimator ratio). Confirmed from the code and the numbers.**
The gateway estimates prompt size in tokens before the call and drops the oldest history turns until the estimate fits under 92 percent of `num_ctx`. The estimate is characters divided by a ratio. The current code uses 4, and a comment records a measured ratio of about 4.5 for this prompt, so 4 is slightly conservative. With the current files the system prompt plus fact sheet is about 22.3K characters. At a ratio of 3 that estimates about 7.4K tokens, and with the 200-token output reserve it already exceeds the 7.5K budget (0.92 x 8192) with zero history, so every turn's history is dropped and follow-ups like "tell me more" lose their context. At a ratio of 4 the estimate is about 5.6K tokens, leaving room for a few turns. The code and arithmetic support the fix. The chars/3 value itself is not in any file I have (the gateway has no version history), so the "before" value comes from the task notes, not from a source.

**2. num_ctx too small for the prompt. Partly confirmed.**
The early README says the prompt and fact sheet were about 1.5K tokens and "fits num_ctx 4096." The fact sheet then grew to about 18K characters. With the prompt that is roughly 5K tokens at the measured ratio, which does not fit in 4096, and Ollama truncates an over-long prompt from the front, which here means the start of the system prompt, where the rules are. The gateway and test runners now use 8192. What I could not confirm is a recorded run where truncation produced a bad answer. The size mismatch is verifiable; the observed failure is not in the files.

**3. Bot repeating unconfirmed figures. Partly confirmed.**
The handover README lists specific figures awaiting approval before publishing, and the current fact sheet no longer has them. The test set includes cases that fail if an answer contains salary-like numbers or claims an unlisted production system. No file records the model quoting an unconfirmed number in a real answer, so treat "the bot quoted it" as the author's recollection until the owner confirms. What is confirmed is that the figures were pulled from the sheet and are guarded by tests.

Other fixes visible in the code: the Worker-supplied visitor IP header is trusted only because the `ask` key is required; the placeholder substitution uses a replacer function so a `$` in the fact sheet cannot be read as a replace pattern; and a forged session id starts a fresh session instead of erroring.

## What I would do next

- Grow the eval set with paraphrase and out-of-sheet questions, and run it on each fact sheet edit, so the sheet is tested like code.
- Save the session checks in the multi-turn result file.
- Deploy the Worker and measure end-to-end latency with the tunnel in the path.
