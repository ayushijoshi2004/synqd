import os
import requests
from requests.auth import HTTPBasicAuth


# Replace these with your real Jira account IDs
JIRA_USERS = {
    "Ria": "712020:bb1dd628-ca13-4d45-baad-a2a6a1e86a0c",
    "Alex": "61a4b1fd9615eb006f1a56db",
    "Maya": "712020:0252193d-9ac1-46f3-9211-7eb033a18c23"
}


class JiraService:
    def __init__(self):
        self.base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        self.email = os.getenv("JIRA_EMAIL", "")
        self.api_token = os.getenv("JIRA_API_TOKEN", "")
        self.project_key = os.getenv("JIRA_PROJECT_KEY", "")

        if not self.base_url:
            raise ValueError("JIRA_BASE_URL is not configured.")

        if not self.email:
            raise ValueError("JIRA_EMAIL is not configured.")

        if not self.api_token:
            raise ValueError("JIRA_API_TOKEN is not configured.")

        if not self.project_key:
            raise ValueError("JIRA_PROJECT_KEY is not configured.")

    def _auth(self):
        return HTTPBasicAuth(
            self.email,
            self.api_token
        )

    def get_account_id(self, owner: str | None):
        if not owner:
            return None

        owner = owner.strip().lower()

        for name, account_id in JIRA_USERS.items():
            if name.lower() == owner:
                return account_id

        return None

    def get_current_user(self):
        response = requests.get(
            f"{self.base_url}/rest/api/3/myself",
            auth=self._auth(),
            headers={
                "Accept": "application/json"
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        return {
            "accountId": data.get("accountId"),
            "displayName": data.get("displayName"),
            "emailAddress": data.get("emailAddress"),
        }

    def search_users(self, query: str):
        if not query:
            return []

        response = requests.get(
            f"{self.base_url}/rest/api/3/user/search",
            params={
                "query": query
            },
            auth=self._auth(),
            headers={
                "Accept": "application/json"
            },
            timeout=15,
        )

        response.raise_for_status()

        users = response.json()

        return [
            {
                "accountId": user.get("accountId"),
                "displayName": user.get("displayName"),
                "emailAddress": user.get("emailAddress"),
                "active": user.get("active"),
            }
            for user in users
        ]

    def get_account_id(self, owner: str | None):
        if not owner:
            return None

        owner = owner.strip()

        # Exact match
        if owner in JIRA_USERS:
            return JIRA_USERS[owner]

        # Case-insensitive match
        owner_lower = owner.lower()

        for name, account_id in JIRA_USERS.items():
            if name.lower() == owner_lower:
                return account_id

        return None

    def create_task(
        self,
        summary: str,
        assignee_account_id: str | None = None,
        description: str | None = None,
    ):
        if not summary:
            raise ValueError("Jira issue summary is required.")

        fields = {
            "project": {
                "key": self.project_key
            },
            "summary": summary,
            "issuetype": {
                "name": "Task"
            },
        }

        # Add assignee if Synqd found a matching Jira user
        if assignee_account_id:
            fields["assignee"] = {
                "accountId": assignee_account_id
            }

        # Optional Jira description
        if description:
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": description
                            }
                        ]
                    }
                ]
            }

        payload = {
            "fields": fields
        }

        response = requests.post(
            f"{self.base_url}/rest/api/3/issue",
            auth=self._auth(),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )

        if not response.ok:
            raise RuntimeError(
                f"Jira issue creation failed. "
                f"Status: {response.status_code}. "
                f"Response: {response.text}"
            )

        data = response.json()

        return {
            "key": data["key"],
            "id": data.get("id"),
            "url": f"{self.base_url}/browse/{data['key']}",
            "assigneeAccountId": assignee_account_id,
        }