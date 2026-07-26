# AI Assistant

**Document:** `modules/18-ai-assistant.md`
**Code:** `bot/modules/ai_assistant/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Answers free-form operational questions from administrators by combining recent monitoring/log/security data with an LLM call, without ever being given write access to any system.

## 2. Responsibilities

- Gather relevant operational context (recent logs, security overview) for a question
- Call the configured AI provider with that context plus a system prompt constraining it to the Bot's actual data
- Return a concise, grounded answer

## 3. Inputs

- Free-form question text (from a future `/ask` command, or any command routed here — see Future Improvements for exact command wiring)
- Recent `audit_logs`, security overview

## 4. Outputs

- Natural-language answer text

## 5. Dependencies

- `bot/integrations/ai_client.py` (Anthropic API)
- `bot/modules/logging/service.py`, `bot/modules/security/service.py`

## 6. Internal Workflow

```
answer_question(question)
   → logging_service.get_recent_command_logs(limit=10)
   → security_service.get_security_overview()
   → build context string
   → ai_client.complete(SYSTEM_PROMPT, context + question)
   ← answer text
```

## 7. Architecture

The system prompt explicitly instructs the model not to invent numbers it wasn't given and to say when data is insufficient — this module is a **read-only summarizer/explainer**, never an executor; it has no path to call any action module (deploy, backup, restore). This is a deliberate architectural boundary, not just a prompt-level one: `ai_assistant/service.py` does not import `deployment`, `backup`, or any other write-capable module.

## 8. Main Functions

- `answer_question(question: str) -> str`

## 9. Error Handling

`ai_client.complete` failures (provider unreachable, misconfigured key) raise `ExternalServiceError` / `ConfigurationError` per the standard taxonomy — the AI Assistant degrades to "AI Assistant is not configured" rather than crashing the Bot when `AI_API_KEY` is unset.

## 10. Security Considerations

- The AI Assistant must never be given tools/function-calling access to write operations in this v1.0 design — this is both a security and a correctness boundary (an LLM should not be the thing deciding to trigger a production deploy)
- Context passed to the model should avoid including raw secrets; current context (logs, security overview) does not include credential values

## 11. Performance Considerations

Each question costs one LLM API call with a bounded context (10 recent logs + security overview) — kept small deliberately to control latency and (if the provider is metered) cost, even though the target providers used here are accessed via free/low-cost tiers where applicable.

## 12. Future Improvements

- Wire to an explicit `/ask <question>` command (not yet in the [Telegram Commands](./17-telegram-commands.md) table — add it there when implemented)
- Expand context sources (monitoring history, deployment history) as those modules mature
- Incident summarization ("summarize this week's incidents") once sufficient `incidents` history exists

## 13. Example Usage

```
Admin: /ask why did the API fail this morning?
Bot: Based on recent logs, the API monitor recorded a "down" status at
     06:14 UTC with no HTTP response, resolving at 06:19 UTC (5 minutes).
     No related security alerts were open at that time. For exact
     latency figures, check /logs or /database.
```

## 14. Related Modules

- [Logging Module](./14-logging-module.md)
- [Security Module](./13-security-module.md)
- [Telegram Commands](./17-telegram-commands.md)
