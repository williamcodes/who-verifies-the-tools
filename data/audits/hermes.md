# Hermes audit — Codex report (recovered from session log)

Recovered 2026-08-28 from Codex session rollout-2026-08-27T17-56-58-01a043b9 (interactive TUI session in the paper repo, message timestamp 2026-08-27T15:55:47.611Z). The frozen audit prompt was applied to a Hermes checkout in a temp directory. Recovered verbatim; the temp paths are the checkout the session used.

---

I found nine formatter discrepancies. The study authors wrote the frozen prompt with prior knowledge of the system’s defects, so these findings are not a blind-discovery result.

The inventory covered 86 statically registered built-in handlers, the three deferred-tool bridge formatters, bundled plugin tools, dynamic MCP pass-through, shared serialization, and the post-format hook. The available eval traces record tool arguments and final answers, but not tool-result payloads, so I constructed representative outputs from the handlers and tests.

1. `session_search` mislabels selected sessions as searched sessions and hides its 300-row scan ceiling.

   The formatter emits `"sessions_searched": len(seen_sessions)` in session_search_tool.py (`session_search_tool.py:940`). For a request returning three lineages, the model sees:

   ```json
   {"count": 3, "sessions_searched": 3}
   ```

   The database search actually requests up to 300 matching message rows (line 781 (`session_search_tool.py:781`)), then stops adding distinct lineages once the requested result limit is reached (line 865 (`session_search_tool.py:865`)). The output neither reports the number of raw rows inspected nor indicates when the 300-row ceiling was reached. An agent would read `sessions_searched` as search coverage, although it is the size of the selected, deduplicated result set.

2. `session_search` presents window sizes as message counts.

   Results contain fields such as:

   ```json
   {"messages_before": 5, "messages_after": 5}
   ```

   The formatter copies those fields in session_search_tool.py (`session_search_tool.py:922`). The storage method calculates them from the returned slice, with each value capped by the requested window (hermes_state.py (`hermes_state.py:11934`)). Thus `5` can mean “at least five,” even when hundreds of messages exist in that direction. Title-match fallback code sometimes assigns a remaining-message total instead (session_search_tool.py (`session_search_tool.py:751`)), so the same field has inconsistent semantics. An agent could conclude that exactly five messages exist before or after the anchor.

3. `session_search` does not identify message IDs as internal SQLite row keys.

   Discovery emits `"match_message_id": 4182` (session_search_tool.py (`session_search_tool.py:898`)), while window messages expose the same value through a generic `"id"` field. The schema calls it only “Message id” (line 1211 (`session_search_tool.py:1211`)).

   The value comes from `messages.id`, an autoincrement SQLite primary key (hermes_state_common.py (`hermes_state_common.py:430`)). It is distinct from `platform_message_id` and `tool_call_id`; the storage documentation states that the external platform identifier is independent of this row key (hermes_state.py (`hermes_state.py:10829`)). An agent could mistake it for a Discord, Telegram, Slack, or tool-call identifier. It is valid only with the corresponding `session_id` in session-search operations.

4. `search_files` reports a captured prefix as the total result count.

   For three matching lines and `limit=2`, the content-mode formatter can produce:

   ```json
   {
     "total_count": 2,
     "matches": [
       {"path": "a.py", "line": 1, "content": "needle"},
       {"path": "b.py", "line": 2, "content": "needle"}
     ]
   }
   ```

   The command is piped through `head -n limit+offset` before parsing (file_operations.py (`file_operations.py:3270`)). The formatter then calls the number of captured rows `total_count` (line 349 (`file_operations.py:349`)). Because the prefix contains exactly `limit+offset` rows, the later truncation test is false (line 3371 (`file_operations.py:3371`)), so the model receives no truncation hint. The same defect affects `files_only` and `count` modes (line 3303 (`file_operations.py:3303`)). An agent would conclude that two matches exist globally, although only two output rows were collected.

5. `search_files` silently truncates every matched line to 500 characters.

   Ripgrep content is sliced with `[:500]` in file_operations.py (`file_operations.py:3351`), then emitted under the unqualified `"content"` field (line 362 (`file_operations.py:362`)). A 505-character line containing only `X` therefore produces a `"content"` value containing exactly 500 `X` characters, with no ellipsis, original length, or per-line truncation flag. The grep fallback repeats this behavior. An agent would treat the value as the complete source line and could miss syntax or evidence in its omitted suffix.

6. Discord server estimates are relabeled as exact counts.

   `server_info` emits:

   ```json
   {"member_count": 123, "online_count": 45}
   ```

   The formatter obtains those values from `approximate_member_count` and `approximate_presence_count` (discord_tool.py (`discord_tool.py:372`)). Its schema describes the action as returning “member counts” (line 661 (`discord_tool.py:661`)). An agent would conclude that the guild has exactly 123 members and 45 online users, although the source fields explicitly designate estimates.

7. Discord member and message result pages omit whether more results exist.

   `search_members` clamps its API request to 100 (discord_tool.py (`discord_tool.py:494`)) and emits only:

   ```json
   {"members": [...], "count": 100}
   ```

   `fetch_messages` does the same (line 520 (`discord_tool.py:520`)) and returns `{"messages":[...],"count":100}` (line 550 (`discord_tool.py:550`)). Neither output includes the applied limit, `has_more`, or a truncation flag. A full 100-item response is indistinguishable from a complete 100-item population, so an agent could report that only 100 members or messages exist.

8. Discord pinned-message content is silently shortened to 200 characters.

   `list_pins` slices each message with `[:200]` (discord_tool.py (`discord_tool.py:561`)) and emits it as ordinary `"content"` (line 565 (`discord_tool.py:565`)). For an input consisting of 200 visible characters followed by `CRITICAL_SUFFIX`, the output contains the first 200 characters with no ellipsis, original length, or truncation field. An agent would conclude that the visible text is the complete pinned message.

9. Deferred `tool_search` records silently abbreviate descriptions and required parameters.

   Each search result record exposes `"description"` and `"required"` as if they were complete (tool_search.py (`tool_search.py:1045`)). The formatter actually limits descriptions to 400 characters, required parameter names to 64 characters, and the required list to 32 entries (line 1005 (`tool_search.py:1005`)). Tests explicitly assert the 32-field and 64-character ceilings.

   A tool with 33 required fields therefore produces a `"required"` array containing only the first 32, without a truncation marker. The model can use this summary to attempt a deferred call without loading the full schema, so it may conclude that the visible fields are exhaustive and invoke the tool without a required argument.