
import json
import os
import time
import uuid
from datetime import datetime, timedelta
import tempfile
import shutil
import argparse
import sys


# Adjust file paths to be relative to the OpenClaw workspace
OPENCLAW_WORKSPACE = os.getenv('OPENCLAW_WORKSPACE', os.path.expanduser('~/.openclaw/workspace'))
KANBAN_FILE = os.path.join(OPENCLAW_WORKSPACE, "tasks.json")
RECOVERY_FILE = os.path.join(OPENCLAW_WORKSPACE, "memory", "kanban_recovery.md")
SCHEMA_URL = "https://openclaw.io/v1/kanban.schema.json"


def _normalize_due_date(due: str | None) -> str | None:
    if due is None: return None
    s = str(due).strip()
    if not s: return None
    if s.endswith('Z'): s = s[:-1] + '+00:00'
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        datetime.fromisoformat(s)
        return s + 'T00:00:00'
    datetime.fromisoformat(s)
    return s

def _parse_custom_fields(fields_list: list[str] | None) -> dict | None:
    if not fields_list: return None
    custom_fields = {}
    for field in fields_list:
        if '=' not in field:
            print(f"Invalid custom field format: {field}. Expected key=value.", file=sys.stderr)
            raise SystemExit(2)
        key, value = field.split('=', 1)
        custom_fields[key.strip()] = value.strip()
    return custom_fields

class KanbanTask:
    def __init__(self, title: str, criticality: str, priority: str,
                 enthusiasm, status: str = "Open", is_milestone: bool = False,
                 history: list = None, id: str = None, due_date: str | None = None,
                 tags: list[str] | None = None, long_description: str | None = None,
                 url: str | None = None, is_subtask: bool = False, parent_task_id: str | None = None,
                 order: int | None = None, task_creator: str | None = None, has_subtasks: bool = False, custom_fields: dict | None = None,
                 blocks: list[str] | None = None, blocked_by: list[str] | None = None, assignee: str | None = None):

        self.id = id if id else str(uuid.uuid4())
        self.title = title
        self.long_description = long_description
        self.url = url
        self.criticality = criticality
        self.priority = priority
        self.is_milestone = is_milestone
        self.due_date = due_date
        self.tags = tags if tags is not None else []
        self.is_subtask = is_subtask
        self.parent_task_id = parent_task_id
        self.order = order
        self.task_creator = task_creator
        self.assignee = assignee
        self.has_subtasks = has_subtasks
        self.custom_fields = custom_fields if custom_fields is not None else {}
        self.blocks = blocks if blocks is not None else []
        self.blocked_by = blocked_by if blocked_by is not None else []
        self.enthusiasm_raw = enthusiasm
        self.enthusiasm_numeric = self._map_enthusiasm_to_numeric(enthusiasm)
        self.status = status
        self.history = history if history is not None else []

    def _map_enthusiasm_to_numeric(self, enthusiasm_val):
        if self.is_milestone: return 0
        if isinstance(enthusiasm_val, int): return enthusiasm_val
        if enthusiasm_val == "!!!!!": return 3
        if enthusiasm_val == "Yay": return 2
        if enthusiasm_val == "Meh": return 1
        return 0

    def _map_enthusiasm_to_display(self):
        if self.is_milestone: return "N/A"
        if isinstance(self.enthusiasm_raw, str): return self.enthusiasm_raw
        if self.enthusiasm_numeric == 3: return "!!!!!"
        if self.enthusiasm_numeric == 2: return "Yay"
        if self.enthusiasm_numeric == 1: return "Meh"
        return "N/A"

    def to_dict(self):
        return {
            "id": self.id, "is_milestone": self.is_milestone, "title": self.title,
            "long_description": self.long_description, "url": self.url, "due_date": self.due_date,
            "criticality": self.criticality, "priority": self.priority,
            "enthusiasm": self.enthusiasm_numeric if not self.is_milestone else None,
            "status": self.status, "history": self.history, "tags": self.tags,
            "is_subtask": self.is_subtask, "parent_task_id": self.parent_task_id,
            "order": self.order, "task_creator": self.task_creator, "assignee": self.assignee,
            "has_subtasks": self.has_subtasks, "custom_fields": self.custom_fields,
            "blocks": self.blocks, "blocked_by": self.blocked_by
        }

    @classmethod
    def from_dict(cls, data):
        enthusiasm_val = data.get("enthusiasm")
        if data.get("is_milestone"): enthusiasm_raw = None
        elif enthusiasm_val == 3: enthusiasm_raw = "!!!!!"
        elif enthusiasm_val == 2: enthusiasm_raw = "Yay"
        elif enthusiasm_val == 1: enthusiasm_raw = "Meh"
        else: enthusiasm_raw = enthusiasm_val
        return cls(
            id=data["id"], title=data.get("title"), long_description=data.get("long_description"),
            url=data.get("url"), criticality=data["criticality"], priority=data["priority"],
            enthusiasm=enthusiasm_raw, status=data.get("status", "Open"),
            is_milestone=data.get("is_milestone", False), history=data.get("history", []),
            due_date=data.get("due_date"), tags=data.get("tags", []),
            is_subtask=data.get("is_subtask", False), parent_task_id=data.get("parent_task_id"),
            order=data.get("order"), task_creator=data.get("task_creator"), assignee=data.get("assignee"),
            has_subtasks=data.get("has_subtasks", False), custom_fields=data.get("custom_fields", {}),
            blocks=data.get("blocks", []), blocked_by=data.get("blocked_by", [])
        )

class ClawKanban:
    def __init__(self):
        self._ensure_recovery_dir()
        self._ensure_kanban_file()
        self.last_read_metadata = {}

    def _ensure_recovery_dir(self):
        os.makedirs(os.path.dirname(RECOVERY_FILE), exist_ok=True)

    def _ensure_kanban_file(self):
        if not os.path.exists(KANBAN_FILE):
            initial_data = {"$schema": SCHEMA_URL, "metadata": {"last_sync": datetime.now().isoformat(), "version": 1, "wip_limits": {}}, "tasks": []}
            with open(KANBAN_FILE, 'w') as f: json.dump(initial_data, f, indent=2)

    def _read_full_data(self):
        try:
            with open(KANBAN_FILE, 'r') as f: full_data = json.load(f)
            self.last_read_metadata = full_data.get("metadata", {})
            return full_data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error reading {KANBAN_FILE}: {e}. Returning empty structure.", file=sys.stderr)
            self.last_read_metadata = {}
            return {"$schema": SCHEMA_URL, "metadata": {"last_sync": datetime.now().isoformat(), "version": 1, "wip_limits": {}}, "tasks": []}

    def _write_full_data(self, full_data):
        fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(KANBAN_FILE), suffix='.tmp')
        try:
            full_data.setdefault("metadata", {})
            full_data["metadata"]["last_sync"] = datetime.now().isoformat()
            with os.fdopen(fd, 'w') as tmp: json.dump(full_data, tmp, indent=2)
            shutil.move(temp_path, KANBAN_FILE)
            self.last_read_metadata = full_data["metadata"]
        except Exception as e:
            os.remove(temp_path)
            print(f"Error writing to {KANBAN_FILE}: {e}. Logging to recovery file.", file=sys.stderr)
            self._log_to_recovery(full_data)
            raise

    def _log_to_recovery(self, full_data):
        timestamp = datetime.now().isoformat()
        with open(RECOVERY_FILE, 'a') as f:
            f.write(f"[{timestamp}] [RECOVERY_PENDING] - Failed to write to {KANBAN_FILE}. State:\n")
            json.dump(full_data, f, indent=2)
            f.write("\n---\n")

    def _get_current_tasks(self):
        full_data = self._read_full_data()
        return {t["id"]: KanbanTask.from_dict(t) for t in full_data.get("tasks", [])}

    def _resolve_stale_check(self, new_tasks_map):
        current_full_data = self._read_full_data()
        on_disk_last_sync_str = current_full_data.get("metadata", {}).get("last_sync")
        if self.last_read_metadata and on_disk_last_sync_str:
            on_disk_last_sync = datetime.fromisoformat(on_disk_last_sync_str)
            internal_last_sync = datetime.fromisoformat(self.last_read_metadata.get("last_sync", datetime.min.isoformat()))
            if on_disk_last_sync > internal_last_sync:
                print(f"B1-SC: Stale-check detected newer file on disk. Re-syncing and merging.")
                current_on_disk_tasks = {t["id"]: KanbanTask.from_dict(t) for t in current_full_data.get("tasks", [])}
                merged_tasks = {**current_on_disk_tasks, **new_tasks_map}
                current_full_data["tasks"] = [task.to_dict() for task in merged_tasks.values()]
                return current_full_data
        current_full_data["tasks"] = [task.to_dict() for task in new_tasks_map.values()]
        return current_full_data

    def add_task(self, title: str, criticality: str, priority: str, enthusiasm, is_milestone: bool = False, actor: str = "Nova",
                 due_date: str | None = None, tags: list[str] | None = None, long_description: str | None = None, url: str | None = None,
                 is_subtask: bool = False, parent_task_id: str | None = None, order: int | None = None, task_creator: str | None = None,
                 assignee: str | None = None, custom_fields: dict | None = None, blocks: list[str] | None = None, blocked_by: list[str] | None = None):
        full_data = self._read_full_data()
        wip_limits = full_data.get("metadata", {}).get("wip_limits", {})
        if "Open" in wip_limits:
            open_tasks = sum(1 for task in full_data.get("tasks", []) if task.get("status") == "Open")
            if open_tasks >= wip_limits["Open"]:
                print(f"Error: WIP limit for 'Open' status ({wip_limits['Open']}) has been reached.", file=sys.stderr); raise SystemExit(2)
        
        new_task = KanbanTask(
            title=title, criticality=criticality, priority=priority, enthusiasm=enthusiasm, is_milestone=is_milestone,
            due_date=due_date, tags=tags, long_description=long_description, url=url, is_subtask=is_subtask,
            parent_task_id=parent_task_id, order=order, task_creator=(task_creator or actor), assignee=assignee,
            custom_fields=custom_fields, blocks=blocks, blocked_by=blocked_by
        )
        new_task.history.append({"timestamp": datetime.now().isoformat(), "event": "Created", "actor": actor})
        current_tasks = {t["id"]: KanbanTask.from_dict(t) for t in full_data.get("tasks", [])}
        current_tasks[new_task.id] = new_task
        if new_task.blocks:
            for other_id in new_task.blocks:
                if other_task := current_tasks.get(other_id):
                    if new_task.id not in other_task.blocked_by: other_task.blocked_by.append(new_task.id)
        if new_task.blocked_by:
            for other_id in new_task.blocked_by:
                if other_task := current_tasks.get(other_id):
                    if new_task.id not in other_task.blocks: other_task.blocks.append(new_task.id)
        if new_task.is_subtask and new_task.parent_task_id:
            if (parent_task := current_tasks.get(new_task.parent_task_id)) and not parent_task.has_subtasks:
                parent_task.has_subtasks = True
                parent_task.history.append({"timestamp": datetime.now().isoformat(), "event": f"Updated: has_subtasks to True", "actor": actor})
        full_data_to_write = self._resolve_stale_check(current_tasks)
        self._write_full_data(full_data_to_write)
        print(f"Added task: '{title}' (ID: {new_task.id})")
        return new_task

    def update_task(self, task_id: str, title: str = None, long_description: str = None, url: str = None, criticality: str = None,
                    priority: str = None, enthusiasm = None, status: str = None, is_milestone: bool = None, actor: str = "Nova",
                    due_date: str | None = None, tags: list[str] | None = None, is_subtask: bool = None, parent_task_id: str | None = None,
                    order: int | None = None, assignee: str | None = None, custom_fields: dict | None = None, blocks: list[str] | None = None,
                    blocked_by: list[str] | None = None):
        current_tasks = self._get_current_tasks()
        if not (task := current_tasks.get(task_id)):
            print(f"Task with ID {task_id} not found.", file=sys.stderr); raise SystemExit(2)
        changes, old_status = [], task.status
        
        if status and status != old_status:
            full_data = self._read_full_data()
            wip_limits = full_data.get("metadata", {}).get("wip_limits", {})
            if status in wip_limits:
                status_count = sum(1 for t in current_tasks.values() if t.status == status)
                if status_count >= wip_limits[status]:
                    print(f"Error: WIP limit for '{status}' status ({wip_limits[status]}) would be exceeded.", file=sys.stderr); raise SystemExit(2)

        if title is not None and task.title != title: changes.append(f"Title to '{title}'"); task.title = title
        if long_description is not None and task.long_description != long_description: changes.append(f"Description updated"); task.long_description = long_description
        if url is not None and task.url != url: changes.append(f"URL to '{url}'"); task.url = url
        if criticality is not None and task.criticality != criticality: changes.append(f"Criticality to '{criticality}'"); task.criticality = criticality
        if priority is not None and task.priority != priority: changes.append(f"Priority to '{priority}'"); task.priority = priority
        if is_milestone is not None and task.is_milestone != is_milestone:
            changes.append(f"Is_milestone to '{is_milestone}'"); task.is_milestone = is_milestone
            if is_milestone: task.enthusiasm_raw, task.enthusiasm_numeric = None, 0
        if enthusiasm is not None and not task.is_milestone:
            new_numeric = task._map_enthusiasm_to_numeric(enthusiasm)
            if task.enthusiasm_numeric != new_numeric: changes.append(f"Enthusiasm to '{enthusiasm}'"); task.enthusiasm_raw, task.enthusiasm_numeric = enthusiasm, new_numeric
        if status is not None and task.status != status: changes.append(f"Status to '{status}'"); task.status = status
        if due_date is not None and task.due_date != due_date: changes.append(f"Due date to '{due_date}'"); task.due_date = due_date
        if tags is not None and task.tags != tags: changes.append(f"Tags to '{tags}'"); task.tags = tags
        if is_subtask is not None and task.is_subtask != is_subtask: changes.append(f"Is_subtask to '{is_subtask}'"); task.is_subtask = is_subtask
        if parent_task_id is not None and task.parent_task_id != parent_task_id: changes.append(f"Parent task to '{parent_task_id}'"); task.parent_task_id = parent_task_id
        if order is not None and task.order != order: changes.append(f"Order to '{order}'"); task.order = order
        if custom_fields is not None:
            original = task.custom_fields.copy(); task.custom_fields.update(custom_fields)
            if original != task.custom_fields: changes.append(f"Custom fields updated")
        if status == "InProgress" and not task.assignee:
             if task.assignee != actor: changes.append(f"Assignee set to '{actor}'"); task.assignee = actor
        if assignee is not None and task.assignee != assignee: changes.append(f"Assignee to '{assignee}'"); task.assignee = assignee
        if status == "Done" and task.blocked_by and (blocking := [tid for tid in task.blocked_by if (t := current_tasks.get(tid)) and t.status not in ["Done", "Archived"]]):
            print(f"Error: Cannot complete task {task_id}, blocked by: {', '.join(blocking)}", file=sys.stderr); raise SystemExit(2)
        if blocks is not None and set(task.blocks) != set(blocks):
            old, new = set(task.blocks), set(blocks)
            for other_id in new - old:
                if (other := current_tasks.get(other_id)) and task_id not in other.blocked_by: other.blocked_by.append(task_id)
            for other_id in old - new:
                if (other := current_tasks.get(other_id)) and task_id in other.blocked_by: other.blocked_by.remove(task_id)
            changes.append(f"Blocks list changed"); task.blocks = blocks
        if blocked_by is not None and set(task.blocked_by) != set(blocked_by):
            old, new = set(task.blocked_by), set(blocked_by)
            for other_id in new - old:
                if (other := current_tasks.get(other_id)) and task_id not in other.blocks: other.blocks.append(task_id)
            for other_id in old - new:
                if (other := current_tasks.get(other_id)) and task_id in other.blocks: other.blocks.remove(task_id)
            changes.append(f"Blocked_by list changed"); task.blocked_by = blocked_by
        if changes:
            task.history.append({"timestamp": datetime.now().isoformat(), "event": f"Updated: {', '.join(changes)}", "actor": actor})
            full_data_to_write = self._resolve_stale_check(current_tasks)
            self._write_full_data(full_data_to_write)
            print(f"Updated task ID: {task_id}")
        else: print(f"No changes for task ID: {task_id}")

    def delete_task(self, task_id: str, actor: str = "Nova"):
        current_tasks = self._get_current_tasks()
        if task_id in current_tasks:
            task = current_tasks.pop(task_id)
            if task.is_subtask and task.parent_task_id and (parent := current_tasks.get(task.parent_task_id)):
                if not any(t.is_subtask and t.parent_task_id == task.parent_task_id for t in current_tasks.values()):
                    parent.has_subtasks = False
                    parent.history.append({"timestamp": datetime.now().isoformat(), "event": "Updated: has_subtasks to False", "actor": actor})
            full_data_to_write = self._resolve_stale_check(current_tasks)
            self._write_full_data(full_data_to_write)
            print(f"Deleted task ID: {task_id} ('{task.title}')")
        else: print(f"Task with ID {task_id} not found.", file=sys.stderr); raise SystemExit(2)

    def show_task(self, task_id: str) -> str:
        if not (task := self._get_current_tasks().get(task_id)):
            print(f"Task with ID {task_id} not found.", file=sys.stderr); raise SystemExit(2)
        out = [f"ID: {task.id}", f"Title: {task.title}", f"Status: {task.status}"]
        if task.task_creator: out.append(f"Creator: {task.task_creator}")
        if task.assignee: out.append(f"Assignee: {task.assignee}")
        out.extend([f"Criticality: {task.criticality}", f"Priority: {task.priority}"])
        if not task.is_milestone: out.append(f"Enthusiasm: {task._map_enthusiasm_to_display()}")
        out.append(f"Milestone: {task.is_milestone}")
        if task.due_date: out.append(f"Due date: {task.due_date}")
        if task.tags: out.append(f"Tags: {task.tags}")
        if task.url: out.append(f"URL: {task.url}")
        if task.is_subtask:
            out.append(f"Subtask: true")
            if task.parent_task_id: out.append(f"Parent task ID: {task.parent_task_id}")
            if task.order is not None: out.append(f"Order: {task.order}")
        if task.has_subtasks: out.append(f"Has Subtasks: true")
        if task.custom_fields:
            out.append(f"Custom Fields:")
            for k, v in task.custom_fields.items(): out.append(f"  - {k}: {v}")
        if task.blocks: out.append(f"Blocks: {', '.join(task.blocks)}")
        if task.blocked_by: out.append(f"Blocked By: {', '.join(task.blocked_by)}")
        if task.long_description: out.append("\nLong Description:\n" + task.long_description)
        if task.history:
            out.append("\nHistory:")
            for ev in task.history: out.append(f"- {ev.get('timestamp')} | {ev.get('actor')} | {ev.get('event')}")
        return "\n".join(out) + "\n"

    def list_tasks(self, sort_by: str = None, limit: int = None, status_filter: list[str] | None = None, tags_filter: list[str] | None = None,
                   tags_mode: str = "any", parent_task_id_filter: str | None = None, is_subtask_filter: bool | None = None,
                   search: str | None = None, creator_filter: str | None = None, format: str = "text", include_done: bool = False,
                   include_archived: bool = False, ranked_view: bool = False):
        tasks = list(self._get_current_tasks().values())
        if status_filter is None:
            if not include_done: tasks = [t for t in tasks if t.status != "Done"]
            if not include_archived: tasks = [t for t in tasks if t.status != "Archived"]
        else: tasks = [t for t in tasks if t.status in status_filter]
        if ranked_view:
            tasks = [t for t in tasks if t.criticality == "Important" or t.priority == "Urgent"]
            sort_by = "priority"
        if tags_filter:
            if tags_mode == "all": tasks = [t for t in tasks if all(tag in t.tags for tag in tags_filter)]
            else: tasks = [t for t in tasks if any(tag in t.tags for tag in tags_filter)]
        if parent_task_id_filter: tasks = [t for t in tasks if t.parent_task_id == parent_task_id_filter]
        if is_subtask_filter is not None: tasks = [t for t in tasks if t.is_subtask == is_subtask_filter]
        if creator_filter:
            cf = creator_filter.strip().lower()
            tasks = [t for t in tasks if (t.task_creator or "").strip().lower() == cf]
        if search:
            q = search.strip().lower()
            tasks = [t for t in tasks if q in (f"{t.title or ''}\n{t.long_description or ''}").lower()]
        
        active = [t for t in tasks if t.status != "Gutter"]
        gutter = [t for t in tasks if t.status == "Gutter"]
        
        def get_sort_key(t):
            return ({"Important": 2, "Not Important": 1}.get(t.criticality, 0),
                    {"Urgent": 2, "Not Urgent": 1}.get(t.priority, 0), t.enthusiasm_numeric,
                    t.due_date if t.due_date else datetime.max.isoformat(), t.order if t.order is not None else -1)

        sort_map = {
            "priority": (get_sort_key, True), "criticality": (lambda t: t.criticality == "Important", True),
            "urgency": (lambda t: t.priority == "Urgent", True), "enthusiasm": (lambda t: t.enthusiasm_numeric, True),
            "due_date": (lambda t: t.due_date if t.due_date else datetime.max.isoformat(), False),
            "order": (lambda t: t.order if t.order is not None else -1, False)
        }
        if sort_by in sort_map:
            key, reverse = sort_map[sort_by]
            active.sort(key=key, reverse=reverse)
        else: active.sort(key=lambda t: t.history[-1]["timestamp"] if t.history else datetime.min.isoformat(), reverse=True)

        sorted_tasks = active + sorted(gutter, key=lambda t: t.history[-1]["timestamp"] if t.history else datetime.min.isoformat())
        if limit: sorted_tasks = sorted_tasks[:limit]
        if not sorted_tasks: return "No tasks in the kanban board." if format == "text" else "[]"
        if format == "json": return json.dumps([t.to_dict() for t in sorted_tasks], indent=2)
        
        output = "ClawKanban Board:\n"
        for t in sorted_tasks:
            output += f"- ID: {t.id}\n  Title: {t.title}\n  Status: {t.status}\n"
        return output

    def set_wip_limit(self, status: str, limit: int):
        full_data = self._read_full_data()
        wip_limits = full_data.get("metadata", {}).get("wip_limits", {})
        if limit > 0:
            wip_limits[status] = limit
            print(f"Set WIP limit for status '{status}' to {limit}.")
        elif status in wip_limits:
            del wip_limits[status]
            print(f"Removed WIP limit for status '{status}'.")
        full_data["metadata"]["wip_limits"] = wip_limits
        self._write_full_data(full_data)

    def get_wip_limits(self):
        full_data = self._read_full_data()
        wip_limits = full_data.get("metadata", {}).get("wip_limits", {})
        if not wip_limits:
            return "No WIP limits are currently set."
        output = "Current WIP Limits:\n"
        for status, limit in wip_limits.items():
            output += f"- {status}: {limit}\n"
        return output

    def report(self):
        tasks = list(self._get_current_tasks().values())
        if not tasks:
            return "No tasks on the board to generate a report."

        status_counts = {}
        for task in tasks:
            status_counts[task.status] = status_counts.get(task.status, 0) + 1

        cycle_times = []
        for task in tasks:
            if task.status in ["Done", "Archived"]:
                in_progress_time, done_time = None, None
                history = sorted(task.history, key=lambda x: x['timestamp'])
                for i, event in enumerate(history):
                    if 'Status to InProgress' in event.get('event', ''):
                        in_progress_time = datetime.fromisoformat(event['timestamp'])
                        for subsequent_event in history[i+1:]:
                            if 'Status to Done' in subsequent_event.get('event', '') or 'Status to Archived' in subsequent_event.get('event', ''):
                                done_time = datetime.fromisoformat(subsequent_event['timestamp'])
                                break
                        if done_time: break
                if in_progress_time and done_time:
                    cycle_times.append(done_time - in_progress_time)

        avg_cycle_time_str = "N/A (no completed tasks with a full cycle)"
        if cycle_times:
            avg_delta = sum(cycle_times, timedelta()) / len(cycle_times)
            days, remainder = divmod(avg_delta.total_seconds(), 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, _ = divmod(remainder, 60)
            avg_cycle_time_str = f"{int(days)} days, {int(hours)} hours, {int(minutes)} minutes"

        output = "ClawKanban Report:\n--------------------\nTasks per Status:\n"
        for status, count in sorted(status_counts.items()):
            output += f"- {status}: {count}\n"
        output += "--------------------\n"
        output += f"Average Cycle Time (First InProgress to First Done): {avg_cycle_time_str}\n"
        return output

def main():
    parser = argparse.ArgumentParser(description="ClawKanban CLI.")
    subparsers = parser.add_subparsers(dest='command', required=True)
    kanban = ClawKanban()

    add_p = subparsers.add_parser('add_task', help='Add a task')
    add_p.add_argument('--title', required=True); add_p.add_argument('--long_description'); add_p.add_argument('--url')
    add_p.add_argument('--criticality', choices=['Important', 'Not Important'], required=True)
    add_p.add_argument('--priority', choices=['Urgent', 'Not Urgent'], required=True)
    add_p.add_argument('--enthusiasm', choices=['!!!!!', 'Yay', 'Meh', '1', '2', '3'], required=True)
    add_p.add_argument('--is_milestone', action='store_true'); add_p.add_argument('--due_date'); add_p.add_argument('--tags', nargs='*')
    add_p.add_argument('--is_subtask', action='store_true'); add_p.add_argument('--parent_task_id'); add_p.add_argument('--order', type=int)
    add_p.add_argument('--task_creator'); add_p.add_argument('--assignee'); add_p.add_argument('--actor', default='Nova')
    add_p.add_argument('--custom_field', action='append'); add_p.add_argument('--blocks', nargs='*'); add_p.add_argument('--blocked_by', nargs='*')

    upd_p = subparsers.add_parser('update_task', help='Update a task')
    upd_p.add_argument('--task_id', required=True); upd_p.add_argument('--title'); upd_p.add_argument('--long_description'); upd_p.add_argument('--url')
    upd_p.add_argument('--criticality', choices=['Important', 'Not Important']); upd_p.add_argument('--priority', choices=['Urgent', 'Not Urgent'])
    upd_p.add_argument('--enthusiasm', choices=['!!!!!', 'Yay', 'Meh', '1', '2', '3'])
    upd_p.add_argument('--status', choices=['Open', 'InProgress', 'Done', 'Archived', 'Gutter'])
    upd_p.add_argument('--is_milestone', choices=['true', 'false']); upd_p.add_argument('--due_date'); upd_p.add_argument('--actor', default='Nova')
    upd_p.add_argument('--tags', nargs='*'); upd_p.add_argument('--is_subtask', choices=['true', 'false']); upd_p.add_argument('--parent_task_id')
    upd_p.add_argument('--order', type=int); upd_p.add_argument('--assignee'); upd_p.add_argument('--custom_field', action='append')
    upd_p.add_argument('--blocks', nargs='*'); upd_p.add_argument('--blocked_by', nargs='*')

    del_p = subparsers.add_parser('delete_task', help='Delete a task')
    del_p.add_argument('--task_id', required=True); del_p.add_argument('--actor', default='Nova')

    show_p = subparsers.add_parser('show_task', help='Show a task')
    show_p.add_argument('--task_id', required=True)
    
    list_p = subparsers.add_parser('list_tasks', help='List tasks')
    list_p.add_argument('--sort_by', choices=['priority', 'criticality', 'urgency', 'enthusiasm', 'due_date', 'order'])
    list_p.add_argument('--limit', type=int); list_p.add_argument('--ranked-view', action='store_true')
    list_p.add_argument('--status_filter', nargs='*', choices=['Open', 'InProgress', 'Done', 'Archived', 'Gutter'])
    list_p.add_argument('--tags_filter', nargs='*'); list_p.add_argument('--tags_mode', choices=['any', 'all'], default='any'); list_p.add_argument('--search')
    list_p.add_argument('--creator_filter'); list_p.add_argument('--parent_task_id_filter')
    list_p.add_argument('--is_subtask_filter', choices=['true', 'false']); list_p.add_argument('--format', choices=['text', 'json'], default='text')
    list_p.add_argument('--include_done', action='store_true'); list_p.add_argument('--include_archived', action='store_true')

    wip_set_p = subparsers.add_parser('set_wip_limit', help='Set WIP limit')
    wip_set_p.add_argument('--status', required=True, choices=['Open', 'InProgress', 'Done', 'Archived', 'Gutter'])
    wip_set_p.add_argument('--limit', type=int, required=True, help="Limit value > 0, or 0 to remove")

    subparsers.add_parser('get_wip_limits', help='Get WIP limits')
    subparsers.add_parser('report', help='Generate metrics report')

    args = parser.parse_args()
    
    kwargs = vars(args).copy()
    command = kwargs.pop('command')
    
    if hasattr(args, 'is_subtask_filter') and args.is_subtask_filter is not None: kwargs['is_subtask_filter'] = args.is_subtask_filter == 'true'
    if hasattr(args, 'is_subtask') and args.is_subtask is not None: kwargs['is_subtask'] = args.is_subtask == 'true'
    if hasattr(args, 'is_milestone') and args.is_milestone is not None: kwargs['is_milestone'] = args.is_milestone == 'true'
    if hasattr(args, 'due_date') and args.due_date is not None:
        try: kwargs['due_date'] = _normalize_due_date(args.due_date)
        except ValueError: print(f"Invalid --due_date: {args.due_date}", file=sys.stderr); raise SystemExit(2)
    if hasattr(args, 'custom_field') and args.custom_field is not None:
        kwargs.pop('custom_field')
        kwargs['custom_fields'] = _parse_custom_fields(args.custom_field)
    
    # Dynamically call the method on the kanban object
    if hasattr(kanban, command):
        method = getattr(kanban, command)
        # Filter kwargs to only those accepted by the method
        import inspect
        sig = inspect.signature(method)
        accepted_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        result = method(**accepted_kwargs)
        if result:
            print(result, end='' if isinstance(result, str) and not result.endswith('\n') else None)
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        raise SystemExit(1)

if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception as e: print(f"ClawKanban fatal error: {e}", file=sys.stderr); raise SystemExit(1)
