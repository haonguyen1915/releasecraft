"""
GitLab API integration for creating merge requests and releases.
"""

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple


class GitLabAPI:
    """GitLab API client for creating merge requests and releases."""

    def __init__(self, project_url: str, token: str = None):
        self.token = token or os.getenv("GITLAB_TOKEN")
        if not self.token:
            raise ValueError(
                "GitLab token not provided. Set GITLAB_TOKEN environment variable or pass token parameter."
            )

        # Parse GitLab project URL to get host and project path
        self.host, self.project_path = self._parse_project_url(project_url)
        self.api_base = f"https://{self.host}/api/v4"
        self.project_id = self._get_project_id()

    def _parse_project_url(self, url: str) -> Tuple[str, str]:
        """Parse GitLab project URL to extract host and project path."""
        # Handle various URL formats
        if url.startswith("git@"):
            # SSH format: git@gitlab.com:user/project.git
            match = re.match(r"git@([^:]+):(.+)(?:\.git)?$", url)
            if match:
                host = match.group(1)
                project_path = match.group(2).replace(".git", "")
                return host, project_path
        elif url.startswith("https://"):
            # HTTPS format: https://gitlab.com/user/project.git
            match = re.match(r"https://([^/]+)/(.+?)(?:\.git)?/?$", url)
            if match:
                host = match.group(1)
                project_path = match.group(2).replace(".git", "")
                return host, project_path

        raise ValueError(f"Unable to parse GitLab URL: {url}")

    def _get_project_id(self) -> str:
        """Get GitLab project ID from project path."""
        encoded_path = urllib.parse.quote(self.project_path, safe="")
        url = f"{self.api_base}/projects/{encoded_path}"

        try:
            response = self._make_request("GET", url)
            return str(response["id"])
        except Exception as e:
            raise ValueError(f"Failed to get project ID for {self.project_path}: {e}")

    def _make_request(self, method: str, url: str, data: dict = None) -> dict:
        """Make HTTP request to GitLab API."""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        request_data = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(
            url, data=request_data, headers=headers, method=method
        )

        try:
            with urllib.request.urlopen(req) as response:
                if response.status in [200, 201]:
                    return json.loads(response.read().decode("utf-8"))
                else:
                    raise Exception(
                        f"HTTP {response.status}: {response.read().decode('utf-8')}"
                    )
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise Exception(f"HTTP {e.code}: {error_body}")
        except Exception as e:
            raise Exception(f"Request failed: {e}")

    def _make_request_list(
        self, method: str, url: str, data: dict = None
    ) -> List[dict]:
        """Make HTTP request to GitLab API and return list response."""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        request_data = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(
            url, data=request_data, headers=headers, method=method
        )

        try:
            with urllib.request.urlopen(req) as response:
                if response.status in [200, 201]:
                    return json.loads(response.read().decode("utf-8"))
                else:
                    raise Exception(
                        f"HTTP {response.status}: {response.read().decode('utf-8')}"
                    )
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise Exception(f"HTTP {e.code}: {error_body}")
        except Exception as e:
            raise Exception(f"Request failed: {e}")

    def get_groups(self) -> List[Dict]:
        """Get all groups accessible to the user."""
        url = f"{self.api_base}/groups?membership=true&order_by=name&per_page=100"
        return self._make_request_list("GET", url)

    def get_subgroups(self, group_id: str) -> List[Dict]:
        """Get subgroups of a specific group."""
        url = f"{self.api_base}/groups/{group_id}/subgroups?per_page=100"
        return self._make_request_list("GET", url)

    def get_projects(
        self, group_id: Optional[str] = None, group_path: Optional[str] = None
    ) -> List[Dict]:
        """Get all projects accessible to the user, optionally filtered by group."""
        query_params = {
            "membership": "true",
            "order_by": "last_activity_at",
            "per_page": "100",
        }

        if group_id and group_path:
            query_params["group_id"] = group_id

        query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
        url = f"{self.api_base}/projects?{query_string}"

        projects = self._make_request_list("GET", url)

        # If a group is selected, filter projects by namespace full_path
        if group_id and group_path:
            return [
                project
                for project in projects
                if (
                    project.get("namespace", {}).get("full_path") == group_path
                    or project.get("namespace", {})
                    .get("full_path", "")
                    .startswith(f"{group_path}/")
                )
            ]

        return projects

    def get_projects_for_group_hierarchy(
        self, group_id: str, group_path: str
    ) -> List[Dict]:
        """Get projects for a specific group and its subgroups."""
        query_params = {
            "membership": "true",
            "order_by": "last_activity_at",
            "per_page": "100",
        }

        query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
        url = f"{self.api_base}/projects?{query_string}"

        all_projects = self._make_request_list("GET", url)

        # Filter projects that belong to the group or its subgroups
        return [
            project
            for project in all_projects
            if (
                project.get("namespace", {}).get("full_path") == group_path
                or project.get("namespace", {})
                .get("full_path", "")
                .startswith(f"{group_path}/")
            )
        ]

    def create_merge_request(
        self, source_branch: str, target_branch: str, title: str, description: str
    ) -> dict:
        """Create a merge request."""
        url = f"{self.api_base}/projects/{self.project_id}/merge_requests"

        data = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
        }

        return self._make_request("POST", url, data)

    def create_release(
        self, tag_name: str, name: str, description: str, ref: str = None
    ) -> dict:
        """Create a GitLab release."""
        url = f"{self.api_base}/projects/{self.project_id}/releases"

        data = {"name": name, "tag_name": tag_name, "description": description}

        if ref:
            data["ref"] = ref

        return self._make_request("POST", url, data)

    def get_project_info(self) -> dict:
        """Get project information."""
        url = f"{self.api_base}/projects/{self.project_id}"
        return self._make_request("GET", url)
