# Synq post-meeting AI pipeline

This is the current implementation report for the attached project. Existing historical README notes may describe earlier in-memory versions. Production still uses CosmosMeetingRepository.

## 1. Exact files created or changed

Paths are relative to the project root. All other original ZIP entries are preserved, including local.settings.json, requirements.txt, host.json, JiraService, the MeetingRepository interface, and the existing seed meetings.

- `backend/AI_PIPELINE.md`
- `backend/ai_provider.py`
- `backend/ai_schema.py`
- `backend/cosmos_meeting_repository.py`
- `backend/fixtures/ai_acceptance_meeting.json`
- `backend/function_app.py`
- `backend/gemini_provider.py`
- `backend/meeting_errors.py`
- `backend/meeting_intelligence.py`
- `backend/meeting_model.py`
- `backend/meeting_service.py`
- `backend/tests/support.py`
- `backend/tests/test_ai_processing.py`
- `backend/tests/test_cosmos_processing.py`
- `backend/tests/test_meetings.py`
- `frontend/package.json`
- `frontend/src/components/calendar/CalendarApprovals.tsx`
- `frontend/src/components/meeting-detail/ActionItemsPanel.tsx`
- `frontend/src/components/meeting-detail/MeetingContent.tsx`
- `frontend/src/components/meeting-detail/MeetingContextPanel.tsx`
- `frontend/src/components/meetings/MeetingFormModal.tsx`
- `frontend/src/pages/CalendarPage.tsx`
- `frontend/src/pages/MeetingDetailPage.tsx`
- `frontend/src/services/calendar.ts`
- `frontend/src/services/meetings.ts`
- `frontend/src/types/meeting.ts`
- `frontend/src/utils/meetingForm.ts`
- `frontend/src/utils/meetings.ts`
- `frontend/tests/ai-processing.test.mjs`

## 2. AIProvider architecture

The processing route calls MeetingService.process(). The service accepts an optional injected AIProvider for testing; otherwise a lazy factory builds GeminiProvider from backend environment variables. AIProvider has one method, analyze(context), returning structured data for independent validation. A future GrokProvider only needs to implement that method and add a factory branch. It does not require changes to routes, persistence, the frontend, or Jira.

No AI framework, agent framework, Grok implementation, or production in-memory fallback was added.

## 3. Gemini SDK/API approach

GeminiProvider uses the existing requests dependency and Gemini's generateContent REST API. The generationConfig requests application/json with responseJsonSchema. The configured model is part of the API path; the API key is sent in a backend-only x-goog-api-key header. No new SDK or dependency is required. Connect/read timeouts are 10/60 seconds, redirects are disabled, and blocked, truncated, non-successful, or malformed responses fail processing.

References checked during implementation:

- https://ai.google.dev/gemini-api/docs/generate-content/structured-output
- https://ai.google.dev/api/generate-content
- https://learn.microsoft.com/en-us/python/api/azure-cosmos/azure.cosmos.containerproxy

## 4. Environment variable names

AI configuration:

- AI_PROVIDER
- AI_MODEL
- GEMINI_API_KEY

Existing Cosmos configuration remains:

- COSMOS_ENDPOINT
- COSMOS_KEY
- COSMOS_DATABASE
- COSMOS_CONTAINER

Existing Jira configuration remains:

- JIRA_BASE_URL
- JIRA_EMAIL
- JIRA_API_TOKEN
- JIRA_PROJECT_KEY

VITE_API_BASE_URL remains the optional, public frontend API-base setting. AI credentials never belong in VITE variables. Existing Functions runtime settings are unchanged. No credentials or configuration values are included in this report, and local.settings.json was not modified.

## 5. AI_MODEL configuration

Gemini is the default provider. AI_MODEL is required and has no hardcoded default. Configure it in the backend process/Functions environment with a model that supports structured output. The provider accepts a model identifier with or without the models/ prefix. Missing or unsupported configuration fails the processing attempt, persists failed when storage is available, and leaves CRUD/Jira startup independent of AI configuration.

## 6. Exact structured AI schema

The following JSON Schema is generated directly from backend/ai_schema.py, the runtime contract. Every listed property is required; unknown properties are rejected again by Python. IDs, sourceMeetingId, Jira metadata, and timestamps are deliberately not model-generated fields. Evidence and participant references are intermediate validation data, not additional Cosmos fields.

```json
{
  "type": "object",
  "properties": {
    "summary": {
      "type": "object",
      "properties": {
        "beforeHighlight": {
          "type": "string"
        },
        "highlight": {
          "type": "string"
        },
        "afterHighlight": {
          "type": "string"
        },
        "points": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      },
      "required": [
        "beforeHighlight",
        "highlight",
        "afterHighlight",
        "points"
      ],
      "additionalProperties": false
    },
    "decisions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "text": {
            "type": "string"
          },
          "participantId": {
            "type": [
              "string",
              "null"
            ]
          },
          "note": {
            "type": "string"
          },
          "evidence": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "entryIndex": {
                  "type": "integer",
                  "minimum": 0
                },
                "quote": {
                  "type": "string"
                }
              },
              "required": [
                "entryIndex",
                "quote"
              ],
              "additionalProperties": false
            }
          }
        },
        "required": [
          "text",
          "participantId",
          "note",
          "evidence"
        ],
        "additionalProperties": false
      }
    },
    "actionItems": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "text": {
            "type": "string"
          },
          "assigneeId": {
            "type": [
              "string",
              "null"
            ]
          },
          "due": {
            "type": "string"
          },
          "status": {
            "type": "string",
            "enum": [
              "todo"
            ]
          },
          "evidence": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "entryIndex": {
                  "type": "integer",
                  "minimum": 0
                },
                "quote": {
                  "type": "string"
                }
              },
              "required": [
                "entryIndex",
                "quote"
              ],
              "additionalProperties": false
            }
          }
        },
        "required": [
          "text",
          "assigneeId",
          "due",
          "status",
          "evidence"
        ],
        "additionalProperties": false
      }
    },
    "unresolvedItems": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "text": {
            "type": "string"
          },
          "evidence": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "entryIndex": {
                  "type": "integer",
                  "minimum": 0
                },
                "quote": {
                  "type": "string"
                }
              },
              "required": [
                "entryIndex",
                "quote"
              ],
              "additionalProperties": false
            }
          }
        },
        "required": [
          "text",
          "evidence"
        ],
        "additionalProperties": false
      }
    },
    "followUps": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": {
            "type": "string"
          },
          "date": {
            "type": "string"
          },
          "startTime": {
            "type": "string"
          },
          "endTime": {
            "type": "string"
          },
          "participantIds": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "agenda": {
            "type": "string"
          },
          "status": {
            "type": "string",
            "enum": [
              "suggested"
            ]
          },
          "evidence": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "entryIndex": {
                  "type": "integer",
                  "minimum": 0
                },
                "quote": {
                  "type": "string"
                }
              },
              "required": [
                "entryIndex",
                "quote"
              ],
              "additionalProperties": false
            }
          }
        },
        "required": [
          "title",
          "date",
          "startTime",
          "endTime",
          "participantIds",
          "agenda",
          "status",
          "evidence"
        ],
        "additionalProperties": false
      }
    },
    "agendaEntries": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "agendaIndex": {
            "type": "integer",
            "minimum": 0
          },
          "title": {
            "type": "string"
          },
          "completed": {
            "type": "boolean"
          },
          "evidence": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "entryIndex": {
                  "type": "integer",
                  "minimum": 0
                },
                "quote": {
                  "type": "string"
                }
              },
              "required": [
                "entryIndex",
                "quote"
              ],
              "additionalProperties": false
            }
          }
        },
        "required": [
          "agendaIndex",
          "title",
          "completed",
          "evidence"
        ],
        "additionalProperties": false
      }
    }
  },
  "required": [
    "summary",
    "decisions",
    "actionItems",
    "unresolvedItems",
    "followUps",
    "agendaEntries"
  ],
  "additionalProperties": false
}
```

Normalization produces the existing Synq structures:

- summary retains beforeHighlight, highlight, afterHighlight, and points.
- decisions contain server-generated id, text, participant, timestamp, and note. An unattributed participant is null.
- actionItems contain server-generated id, text, assignee, due, and todo status. An unknown assignee is null. Existing Jira fields are retained only from persisted data.
- unresolvedItems is an optional string array, the one new intelligence field needed because the original app had no unresolved-item representation.
- followUps use the existing model with server-generated id, sourceMeetingId, suggested status, inherited project/team, and supported meeting fields. Unknown date/startTime/endTime values are empty strings; unspecified attendees are an empty array. Approved meetings still require a complete valid schedule and participants.
- agendaEntries retains its existing title/timestamp/completed structure. There is no agendaProgress field.

## 7. Validation and normalization

Raw provider output is never written to Cosmos. Python strictly checks object properties, arrays, strings, nullable participant references, integer indices, booleans, and status enums. Null/malformed root output, unknown fields, supplied IDs/Jira fields, unknown people, invented agenda entries, and invalid schedules fail the entire result before any intelligence is committed.

Every extracted decision, task, unresolved item, follow-up, and completed agenda entry needs a verbatim quote from a valid transcript index. Completed agenda evidence must be substantive rather than a single keyword. Task deadline text must appear in its supporting quote. Follow-up dates are conservatively checked against explicit calendar references or the source meeting's relative date; times must appear in evidence. Unclear timing remains blank. No arbitrary duration or end time is supplied.

The model remains responsible for interpreting meaning and attribution. These checks constrain references and structure; they cannot prove that every natural-language interpretation is correct. Users review tasks and follow-ups before taking external action.

## 8. Safe merge behavior

Processing first persists aiStatus=processing. The transcript, existing agenda entries, participants, and limited meeting metadata are sent to the provider. Jira credentials, Jira links, unrelated meetings, and documents are not sent.

On success, validated summary, decisions, unresolvedItems, and the matched agendaEntries refresh the analysis. Action items and follow-ups are added without replacing existing items. Stable UUIDs and normalized task text/follow-up titles prevent exact repeated extraction from duplicating items. Existing task IDs, statuses, Jira metadata, edited follow-ups, approved/dismissed states, and scheduledMeetingId links remain intact.

The final merge runs against the latest repository record. If the transcript, agenda, or relevant context changed during processing, the stale result is discarded and the attempt fails. The original transcript, participants, lifecycle status, preview, meeting metadata, and project/team details are preserved.

## 9. Action items and Jira

New AI tasks start todo. IDs are generated by Python; an owner is copied from known participant/speaker data only when the provider supplies a valid attribution. Unknown owners render as Unassigned.

The existing Create Jira Ticket button and meeting action-item Jira route are unchanged. The real Jira integration creates the issue, then persists its returned key and URL on the action item. Processing never creates Jira issues or fabricates Jira metadata, and reprocessing cannot reset a linked task's stored completion status. Creating an issue still does not count as completing the task.

## 10. Suggested follow-ups

AI suggestions are stored inside the existing source meeting's followUps. Their status is always suggested. Missing scheduling information remains blank and missing attendees remain unspecified. They appear in the existing Calendar approvals panel with Date/Time to be chosen labels, and incomplete schedules are excluded from the calendar grid.

The existing edit form can save an incomplete review draft. Approval still requires title, valid date/start/end times, and participants, and uses the existing backend approval endpoint. Dismiss uses the existing dismiss endpoint. Neither processing nor validation schedules/approves suggestions, sends invitations, or creates Google Calendar events.

## 11. Existing agenda completion

Results must include exactly one match for every existing agenda entry, using its original index and exact title. Order and titles are preserved. Covered entries receive completed=true only with supporting transcript evidence; uncovered entries receive completed=false. The provider cannot add, omit, duplicate, or rename agenda entries.

Frontend meeting creation and agenda edits now save the user-entered agendaEntries to the backend. Editing unrelated meeting metadata preserves stored entries and completion states. For an older document containing only the agenda text field, edit/save its agenda before processing so there are stored entries to evaluate.

## 12. Agenda timestamps

The provider cannot return a timestamp field. Python copies a valid elapsed timestamp only from a cited transcript entry. When no reliable timestamp is available, an agenda entry retains its existing timestamp, or remains empty. Decisions without a reliable source timestamp remain empty. No timestamp is synthesized from transcript order or assumed speaking duration.

## 13. Cosmos persistence and concurrency

The existing production composition remains HTTP route to MeetingService to MeetingRepository to CosmosMeetingRepository. The same meeting document and existing container store processing state and all successful intelligence. No container, database, partition scheme, or infrastructure is created or changed.

Cosmos updates now use ETag conditional replacement. Pure processing/Jira persistence callbacks retry conflicts against the latest record, preserving concurrent changes. Callbacks with external/create side effects are not blindly replayed. A follow-up approval whose source write conflicts removes the meeting created by that unsuccessful attempt rather than leaving an orphan.

Completed intelligence, agenda ticks, task/Jira metadata, and follow-up state persist in Cosmos across frontend and backend restart. Offline tests exercise the actual adapter with a durable container double and fresh repository/service instances; they do not constitute a live-cloud acceptance test.

## 14. Failure behavior

Provider quota/auth/network/timeout failures, invalid configuration, blocked output, and invalid intelligence produce an actual 503 JSON error with code ai_processing_failed. The service attempts to persist aiStatus=failed while preserving all saved transcript, intelligence, agenda entries, and Jira metadata. The frontend shows: "AI processing unavailable. Your meeting and transcript are still saved." It exposes Retry processing and uses persisted backend data after responses and refresh.

An unknown meeting returns 404. A missing/blank transcript returns 400 without starting processing. An already-processing meeting returns 409. No fake response, mock summary, canned AI result, or alternate-provider fallback is used by this pipeline.

## 15. Tests and builds

Verified with Python 3.13 and the existing backend requirements:

```sh
cd backend
python -m unittest discover -s tests -v
```

71 backend tests pass, including all existing meeting CRUD, Jira, and follow-up tests. New cases cover structured extraction, stable IDs, todo/suggested statuses, unknown owners/timing, agenda matching/coverage/timestamps, invalid output, provider failures/retry, Jira preservation, reprocessing, concurrent writes, and persistence through a fresh Cosmos adapter/service over an offline durable container double. Gemini HTTP calls are mocked; all processing tests inject a mock provider.

Verified from frontend/:

```sh
npm run typecheck
npm run test:jira
npm run test:ai
npm run build
```

Typecheck and production build pass. The Jira suite reports 6 passing tests; the AI suite reports 9 passing tests (these counts include each suite's parent test). Frontend checks cover stored data hydration, pending state, failure/retry UI, unknown owners, incomplete follow-up review, Jira linkage, refresh with new module state, and preservation of agenda ticks when editing metadata. HTTP is stubbed and component checks use static rendering; no real Gemini or Jira calls occur.

The manual input fixture also validates against the existing meeting CRUD schema. No test changes local.settings.json or connects to live Cosmos.

## 16. Exact manual acceptance steps

1. Configure the AI environment names listed above in the backend process. Retain the existing Cosmos and Jira configuration. Install backend requirements into your normal Python 3.13 environment and start the existing app with func start. Start the frontend with npm run dev.
2. From backend/, create the supplied input-only fixture using the existing API. It is not loaded by production seeding and contains no generated intelligence or Jira metadata:

   ```sh
   curl --fail-with-body -sS -X POST http://localhost:7071/api/meetings \
     -H 'Content-Type: application/json' \
     --data-binary @fixtures/ai_acceptance_meeting.json
   ```

3. Save the returned meeting ID. Refresh the Meetings screen and open Synq AI acceptance review. The transcript discusses QA and the launch timeline, but does not discuss Budget. The agenda should initially show all three unchecked.
4. Click Process Meeting. While the request runs, verify the processing label and disabled processing button. A simultaneous GET /api/meetings/{meeting_id} should show aiStatus=processing once the server has claimed the request. The processing endpoint is POST /api/meetings/{meeting_id}/process.
5. On success, inspect both the UI and GET response. Verify processed status; a concise transcript-based summary; the launch decision; Alex's checklist task with todo status; the unresolved support-ownership question; and a suggested support review. No Jira key/URL should exist on the new task. No meeting should have been scheduled by processing.
6. Verify the original agenda titles/order remain. QA status and Launch timeline should be completed; Budget should remain incomplete. Supported timestamps must come from the saved transcript. The untimed support-review suggestion must have no invented date/start/end time or attendees.
7. Open Calendar. Verify the suggestion appears in Awaiting approval without an invented calendar placement. Review/edit it, fill the missing schedule and participants, then approve. Alternatively dismiss it. Verify the existing backend flow stores the resolution and, only on approval, creates the scheduled meeting.
8. On Meeting Detail, click Create Jira Ticket for the AI-generated checklist task. Verify the real issue exists in your configured Jira project, and the actual jiraIssueKey/jiraIssueUrl are returned and stored in Cosmos. The task must remain todo unless the user separately completes it.
9. Refresh the browser, then stop and restart both backend and frontend. GET the meeting again and reopen its detail. Summary, decisions, action items, unresolved items, follow-up state, Jira metadata, and agenda completion/timestamps must be unchanged.
10. Reprocess the same transcript. Verify linked tasks retain their IDs/Jira fields/status, and the resolved follow-up is not returned to suggested. Wording can vary with a real model; inspect newly extracted tasks before creating further tickets.
11. In a local acceptance environment, temporarily remove an AI configuration variable from the backend process, restart, and process again. Expect 503 and persisted failed status. Compare all saved intelligence/agenda/transcript/Jira fields with the prior GET: they must be unchanged. Restore configuration, restart, click Retry processing, and verify success. Missing AI configuration must not disable meeting CRUD or Jira routes.
12. Create a meeting without a transcript. The UI must not enable processing; calling the endpoint directly must return 400 without inventing results.

## 17. Remaining issues and scope limits

- Live Gemini/Cosmos/Jira acceptance has not been executed here. AI_MODEL and GEMINI_API_KEY were not configured in the execution environment. No real Jira issue was created and no cloud meeting was changed during verification. Model availability/quota and the final live outputs must be checked with the steps above.
- Processing is synchronous with bounded provider timeouts. If the backend process is forcibly killed mid-request, a meeting can remain marked processing. After confirming that request is no longer running, reset only aiStatus to failed through the existing PATCH meeting endpoint, then retry. No job queue, worker lease, or new infrastructure was introduced.
- If Cosmos itself is unavailable, no application can guarantee that a failed-status update is persisted. Existing intelligence is not replaced with fallback data; the request still fails.
- Exact repeated extraction is deduplicated. Semantically equivalent but differently worded tasks/follow-up titles may still need user review; no semantic matching or cross-meeting system was added.
- Existing task-status editing and the separate canned assistant/demo proposal behavior were not redesigned. This pipeline's generated intelligence never falls back to them.
- No Vexa, live agent, ElevenLabs, Google Calendar, Azure AI, Grok, document ingestion, RAG, embeddings, vector search, project memory, cross-meeting AI, authentication, or cloud resources were added.
