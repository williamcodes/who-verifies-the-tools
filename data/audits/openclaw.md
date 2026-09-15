Study disclosure: the study authors wrote this frozen prompt knowing the system’s defects. The 10 source-verified findings below, plus one trace-only finding, must be interpreted with that prior knowledge.

## Findings

1. System-agent promises a mutation that can still be rejected.

   Formatter: `src/agents/tools/system-agent-tool.ts:500-512`

   Output:

   > the host accepted this exact approved action and will apply it after this turn. Do not call it again.

   At that point, the tool has only recorded an `approved-operation` directive. The host revalidates inference authority before applying it at `src/system-agent/chat-turn-router.ts:471-483`. A credential change can fail that check without calling the mutation, as proved by `src/system-agent/chat-turn-router.operations.test.ts:232-275`.

   The model wrongly concludes that the mutation is guaranteed and should not be retried.

2. Google Meet reports `joined: true` while the agent is still waiting in the lobby.

   Formatter: `extensions/google-meet/src/create.ts:153-157`

   Representative output:

   ```json
   {
     "joined": true,
     "nextAction": "Share meetingUri with participants; the OpenClaw agent has started the join flow.",
     "join": {
       "session": {
         "state": "active",
         "chrome": {
           "health": {
             "inCall": false,
             "lobbyWaiting": true
           }
         }
       }
     }
   }
   ```

   The session gets internal state `active` immediately at `src/meeting-bot/session-factory.ts:34-41`. The supported join outcome can still contain `inCall:false`, `lobbyWaiting:true`, and `meet-admission-required`; `extensions/google-meet/index.test.ts:3762-3840` proves that this outcome returns successfully.

   The model wrongly concludes that the participant entered the meeting and may invite others to a meeting where the agent remains outside.

3. `attachments_fetch` says a message does not exist after searching only a bounded recent window.

   Formatter: `src/mcp/channel-tools.ts:88-103`

   Output:

   > message not found: `<message_id>`

   The tool reads 100 recent messages by default and permits at most 200. The cap is enforced at `src/mcp/channel-bridge.ts:258-269`. It does not search older history before returning the error.

   The model wrongly concludes that the identifier is invalid or absent from the conversation, when the message may simply be older than the scanned window.

4. `conversations_list` applies its channel filter after limiting an unfiltered session list.

   Formatter: `src/mcp/channel-tools.ts:34-49`, through `src/mcp/channel-shared.ts:190-197`

   Representative output:

   ```text
   conversations: 0

   {
     "conversations": []
   }
   ```

   The bridge requests at most 50 sessions by default, then filters those returned rows by channel at `src/mcp/channel-bridge.ts:222-240`. The Gateway request does not receive the channel filter.

   The model wrongly concludes that no matching conversation exists. Matching conversations can exist beyond the first unfiltered page. The output contains no cursor or truncation marker.

5. `suggest_task` hides eviction of an earlier pending suggestion.

   Formatter: `src/agents/tools/task-suggestion-tools.ts:104-116`

   Output:

   ```json
   {
     "task_id": "task_…"
   }
   ```

   The registry is capped at 100 entries and 2 MiB at `src/gateway/task-suggestion-registry.ts:9-10`. Creating a new suggestion may delete pending suggestions at `src/gateway/task-suggestion-registry.ts:32-59` and `src/gateway/task-suggestion-registry.ts:76-93`. The Gateway broadcasts those cards as expired but returns only the new suggestion at `src/gateway/server-methods/task-suggestions.ts:545-563`. The 101st-create behavior is proved by `src/gateway/server-methods/task-suggestions.test.ts:938-973`.

   The model wrongly concludes that it only created a card. Its action may also have removed an earlier operator-visible follow-up.

6. Provider fallback `web_fetch` fabricates authoritative-looking metadata.

   Formatter: `src/agents/tools/web-fetch.ts:590-654`, serialized by `src/agents/tools/tool-results.ts:10-11`

   A provider payload containing only `{text:"body"}` becomes output containing fields such as:

   ```json
   {
     "finalUrl": "<requested URL>",
     "status": 200,
     "extractor": "<provider id>",
     "rawLength": 4,
     "fetchedAt": "<normalization time>",
     "tookMs": "<pre-provider elapsed time>"
   }
   ```

   Actual behavior:

   - Missing `status` becomes `200` at `src/agents/tools/web-fetch.ts:612-615`.
   - Missing `finalUrl` becomes the requested URL at `src/agents/tools/web-fetch.ts:610-611`.
   - Missing `rawLength` becomes the extracted text length at `src/agents/tools/web-fetch.ts:606-609`.
   - Missing `fetchedAt` becomes the normalization time at `src/agents/tools/web-fetch.ts:644-647`.
   - Missing `tookMs` uses elapsed time measured before provider execution at `src/agents/tools/web-fetch.ts:657-680` and `src/agents/tools/web-fetch.ts:753-765`.

   The model cannot distinguish provider-reported facts from synthesized defaults. It can wrongly infer a recorded HTTP 200, an observed final URL, a source-document length, an actual fetch timestamp, and complete provider latency.

7. Shared provider formatting says audio is attached after serializers drop it.

   Formatter: `packages/ai/src/providers/tool-result-text.ts:146-154`

   Output:

   > (see attached audio)

   Mixed image and audio produce:

   > (see attached media)

   The main serializers emit text and images, with no audio representation:

   - Google: `packages/ai/src/providers/google-shared.ts:306-338`
   - OpenAI Chat Completions: `packages/ai/src/openai-completions-messages.ts:252-278`
   - OpenAI Responses: `packages/ai/src/transports/openai-responses-replay-messages-internal.ts:481-508`
   - Anthropic: `packages/ai/src/transports/anthropic-transport-stream.ts:283-300`
   - Mistral: `packages/ai/src/providers/mistral.ts:932-961`

   Existing tests preserve the claim at `packages/ai/src/providers/openai-responses-shared.test.ts:716-760`.

   The model wrongly concludes that audio bytes are available elsewhere in the request. In mixed results, only the image is attached.

   Reachability caveat: the current typed `ToolResultMessage` permits text and images at `packages/llm-core/src/types.ts:375-382`. The audio test casts through `unknown`, so the formatter defect is verified while normal typed production reachability remains unproved.

8. xAI’s final compatibility formatter describes media after discarding it.

   Formatter: `extensions/xai/stream.ts:136-213`

   Outputs include:

   > (see attached image)  
   > (see attached audio)  
   > (see attached media)

   `normalizeXaiResponsesFunctionCallOutput` retains text and optionally collects images. It never collects audio or other media, then replaces the original output array with one of those strings. Tests explicitly prove the dropped-image and dropped-audio cases at `extensions/xai/stream.test.ts:738-788`.

   The model wrongly concludes that discarded media remains attached. Normal typed image results may be downgraded earlier, so reachability through every standard path is unproved.

9. Memory-flush append reports a byte-for-byte no-op as a change.

   Formatter: `src/agents/agent-tools.read.ts:805-810`

   Output:

   > Appended content to `memory/…`.

   Details:

   ```json
   {"changed":true}
   ```

   Empty content is valid under the inherited schema at `src/agents/sessions/tools/write.ts:35-41`. If an existing sandbox file already ends in a newline, appending `""` constructs identical content at `src/agents/agent-tools.read.ts:705-728`, yet the formatter always reports success and `changed:true`.

   The model wrongly concludes that memory changed.

10. LanceDB adds ellipses to text that was neither changed nor truncated.

   Formatters:

   - `extensions/memory-lancedb/index.ts:431-440`
   - `extensions/memory-lancedb/index.ts:510-526`

   For the exact stored text `likes tea`, the acknowledgment is:

   > Stored: "likes tea..."

   Candidate previews receive the same unconditional suffix. The database stored the exact original text.

   The model sees what looks like a truncated or altered quotation even when the full value is shown.

## Trace-only finding

The checked-in live Claude CLI capture at `test/fixtures/cli/claude-2.1-subagent-forwarding.jsonl:61` contains:

> ... 4 lines omitted ...  
> [tokenjuice] This is the complete, authoritative output for this command.

It then instructs the model not to rerun the command. The output contradicts itself and can cause an agent to treat a partial directory listing as exhaustive.

OpenClaw adopts Tokenjuice-rewritten `content` at `extensions/tokenjuice/tool-result-middleware.ts:77-92`, but the exact formatter lives in the `tokenjuice` dependency imported at `extensions/tokenjuice/runtime-api.ts:2`. Dependencies are absent from this checkout, so I could not attribute this trace to the currently pinned Tokenjuice 0.8.1 implementation with source-level certainty.

## Inventory coverage

I reviewed the model-facing result boundary, rather than terminal-only UI rendering:

- 171 explicit tool execution implementations across 113 production files.
- 210 production files containing result-content construction or forwarding.
- Core filesystem, exec/process, search, web, media, message, session, subagent, system-agent, task, terminal, transcript, TTS, node, gateway, and utility tools.
- Registered plugin tools for Canvas, ClickClack, Diffs, Feishu, file transfer, Firecrawl, Google Meet, LLM Task, Lobster, memory-core, memory-lancedb, memory-wiki, Ollama, 1Password, QA, Tavily, voice call, WhatsApp, Workboard, and Zalo.
- Channel action result paths for Discord, Slack, Telegram, Matrix, Signal, Google Chat, iMessage, LINE, Mattermost, Teams, Nextcloud Talk, Twitch, Zalo, and WhatsApp.
- Provider replay formatters for Anthropic, Google, OpenAI, Mistral, Ollama, and xAI.
- MCP channel/plugin handlers, node-host MCP bounds, tool-search projections, middleware rewriting, and checked-in tool-call traces.

No additional verified mismatch was found in those reviewed surfaces.

I inspected OpenClaw’s Codex-side dynamic-tool and transcript projections, but I issue no Codex verdict. The mandatory sibling `../codex` checkout is absent, and the read-only environment prevented cloning it.

Tests could not start because dependencies are absent and the read-only sandbox blocked Corepack cache creation. The findings are backed by source and existing boundary tests. No files were changed.