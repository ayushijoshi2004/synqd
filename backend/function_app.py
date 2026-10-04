import azure.functions as func
import json
import logging
import os
from http.cookies import SimpleCookie
from html import escape
from cosmos_meeting_repository import CosmosMeetingRepository

from meeting_service import MeetingService
from seed_data import load_seed_meetings
from api_http import json_response, read_body, respond
from meeting_errors import MeetingError
from jira_service import JiraService
from google_calendar import GoogleCalendar, CalendarError, CalendarConfigError, COOKIE_NAME, settings

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
repository = CosmosMeetingRepository(
    endpoint=os.environ["COSMOS_ENDPOINT"],
    key=os.environ["COSMOS_KEY"],
    database_name=os.environ["COSMOS_DATABASE"],
    container_name=os.environ["COSMOS_CONTAINER"],
)

# Seed demo meetings only on the very first run.
if not repository.list():
    for meeting in load_seed_meetings():
        repository.create(meeting)

def get_google_calendar():
    # Optional integration: missing settings never disable CRUD, AI, or Jira.
    config = settings()
    from google_calendar_store import GoogleCalendarStore
    try:
        store = GoogleCalendarStore(repository.container, config["GOOGLE_TOKEN_ENCRYPTION_KEY"])
    except (ValueError, TypeError):
        raise CalendarConfigError("Google Calendar encryption configuration is invalid.") from None
    return GoogleCalendar(store, config)


meetings = MeetingService(repository, calendar_factory=lambda: get_google_calendar())

_jira_service = None


def get_jira() -> JiraService:
    # Built on first Jira request, not at import, so missing JIRA_* settings
    # cannot stop the Cosmos-backed meeting API from starting.
    global _jira_service
    if _jira_service is None:
        _jira_service = JiraService()
    return _jira_service


@app.route(route="jira-test", methods=["GET"])
def jira_test(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return json_response(get_jira().test_connection())
    except Exception as exc:
        return json_response(
            {
                "error": {
                    "code": "jira_error",
                    "message": str(exc),
                }
            },
            500,
        )


@app.route(
    route="meetings/{meeting_id}/action-items/{action_item_id}/jira",
    methods=["POST"],
)
def create_jira_for_action_item(req: func.HttpRequest) -> func.HttpResponse:
    try:
        action_item, created = meetings.create_jira_issue(
            req.route_params["meeting_id"],
            req.route_params["action_item_id"],
            get_jira(),
        )
        return json_response(action_item, 201 if created else 200)
    except MeetingError as exc:
        return json_response({"error": {"code": exc.code, "message": str(exc)}}, exc.status_code)
    except Exception:
        logging.exception("Unexpected Jira action-item failure")
        return json_response({"error": {"code": "internal_error", "message": "Unable to complete the request."}}, 500)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"status": "working"}),
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="meetings", methods=["GET"])
def list_meetings(req: func.HttpRequest) -> func.HttpResponse:
    return respond(meetings.list)


@app.route(route="meetings", methods=["POST"])
def create_meeting(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.create(read_body(req)), created=True)


@app.route(route="meetings/{id}", methods=["GET"])
def get_meeting(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.get(req.route_params["id"]))


@app.route(route="meetings/{id}", methods=["PATCH"])
def patch_meeting(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.patch(req.route_params["id"], read_body(req)))


@app.route(route="meetings/{meeting_id}/ask", methods=["POST"])
def ask_meeting(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.ask(req.route_params["meeting_id"], read_body(req)))


@app.route(route="meetings/{meeting_id}/process", methods=["POST"])
def process_meeting(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.process(req.route_params["meeting_id"]))


@app.route(route="meetings/{id}", methods=["DELETE"])
def delete_meeting(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.delete(req.route_params["id"]))


@app.route(
    route="meetings/{meeting_id}/follow-ups/{follow_up_id}/dismiss",
    methods=["POST"],
)
def dismiss_follow_up(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.dismiss_follow_up(
        req.route_params["meeting_id"], req.route_params["follow_up_id"],
    ))


@app.route(
    route="meetings/{meeting_id}/follow-ups/{follow_up_id}/approve",
    methods=["POST"],
)
def approve_follow_up(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.approve_follow_up(
        req.route_params["meeting_id"], req.route_params["follow_up_id"], read_body(req),
    ))


@app.route(route="meetings/{meeting_id}/follow-ups/{follow_up_id}/google-calendar", methods=["POST"])
def retry_follow_up_calendar(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.sync_follow_up_calendar(
        req.route_params["meeting_id"], req.route_params["follow_up_id"],
    ))


@app.route(route="google-calendar/status", methods=["GET"])
def google_calendar_status(req: func.HttpRequest) -> func.HttpResponse:
    def status():
        try:
            return get_google_calendar().status()
        except CalendarConfigError as exc:
            return {"configured": False, "connected": False, "error": str(exc)}
    response = respond(status)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route(route="google-calendar/authorize", methods=["GET"])
def google_calendar_authorize(req: func.HttpRequest) -> func.HttpResponse:
    try:
        calendar = get_google_calendar()
        url, binding = calendar.start_authorization()
        secure = "; Secure" if calendar.config["GOOGLE_REDIRECT_URI"].startswith("https:") else ""
        return func.HttpResponse(status_code=302, headers={
            "Location": url, "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "Set-Cookie": f"{COOKIE_NAME}={binding}; HttpOnly; SameSite=Lax; Path=/api/google-calendar; Max-Age=600{secure}",
        })
    except CalendarError as exc:
        return json_response({"error": {"code": exc.code, "message": str(exc)}}, exc.status_code)
    except Exception:
        return json_response({"error": {"code": "google_calendar_error", "message": "Unable to start Google Calendar authorization."}}, 503)


@app.route(route="google-calendar/callback", methods=["GET"])
def google_calendar_callback(req: func.HttpRequest) -> func.HttpResponse:
    status, message = 200, "Google Calendar connected. Close this tab and return to Synq."
    try:
        cookies = SimpleCookie(req.headers.get("Cookie", ""))
        cookie = cookies.get(COOKIE_NAME)
        get_google_calendar().finish_authorization(
            req.params.get("state", ""), cookie.value if cookie else "",
            req.params.get("code", ""), req.params.get("error"),
        )
    except CalendarError as exc:
        status, message = 400, str(exc)
    except Exception:
        status, message = 503, "Unable to save Google Calendar authorization. Return to Synq and connect again."
    return func.HttpResponse(
        "<!doctype html><html><head><title>Synq Google Calendar</title></head><body><p>" + escape(message) + "</p></body></html>",
        mimetype="text/html", status_code=status, headers={
            "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "Set-Cookie": f"{COOKIE_NAME}=; HttpOnly; SameSite=Lax; Path=/api/google-calendar; Max-Age=0",
        },
    )


@app.route(route="meetings/join", methods=["POST"])
def join_meeting(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.join_meeting(read_body(req)))


@app.route(route="meetings/{meeting_id}/transcript", methods=["GET"])
def get_meeting_transcript(req: func.HttpRequest) -> func.HttpResponse:
    response = respond(lambda: meetings.get(req.route_params["meeting_id"]))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route(route="meetings/{meeting_id}/transcription/end", methods=["POST"])
def end_transcription(req: func.HttpRequest) -> func.HttpResponse:
    return respond(lambda: meetings.end_transcription(req.route_params["meeting_id"]))


@app.timer_trigger(schedule="*/10 * * * * *", arg_name="timer", run_on_startup=False, use_monitor=False)
def poll_transcriptions(timer: func.TimerRequest) -> None:
    meetings.poll_transcriptions()
