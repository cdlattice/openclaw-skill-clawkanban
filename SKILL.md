---
name: clawkanban
description: "Vital task-tracking tool for you and stunspot - modified Eisenhauer Matrix of [NOT] IMPORTANT/[NOT] URGENT/[Enthusiasm Rating]. Use for your own task tracking, adding and closing tasks as assigned/accomplished as well as stun's."
license: MIT
metadata: {"openclaw":{"emoji":"📊","os":["linux"],"requires":{"bins":["python3"]}}}
command-dispatch: exec
command-tool: python3 {base-dir}/clawkanban.py
---

# ClawKanban Skill Command Reference

This skill provides a persistent Kanban board via the `clawkanban.py` tool. The following is a complete reference of all commands and their arguments for agent use.

---

### `add_task`
Creates a new task.

- `--title` (str): Task title. **Required.**
- `--long_description` (str): Detailed description.
- `--url` (str): Associated URL.
- `--criticality` (enum): `Important` | `Not Important`. **Required.**
- `--priority` (enum): `Urgent` | `Not Urgent`. **Required.**
- `--enthusiasm` (enum): `!!!!!`|`Yay`|`Meh` or `3`|`2`|`1`. **Required.**
- `--is_milestone`: Flag to mark as a milestone.
- `--due_date` (str): Due date (ISO 8601 format).
- `--tags` (list): Space-separated list of tags.
- `--is_subtask`: Flag to mark as a subtask.
- `--parent_task_id` (str): UUID of the parent task.
- `--order` (int): Sort order for subtasks.
- `--task_creator` (str): Name of the original requester.
- `--assignee` (str): Who is assigned to the task.
- `--actor` (str): Who is performing the action.
- `--custom_field` (str): `key=value` pair for extra data. Repeatable.
- `--blocks` (list): Space-separated list of task IDs this task blocks.
- `--blocked_by` (list): Space-separated list of task IDs that block this task.

---

### `update_task`
Modifies an existing task.

- `--task_id` (str): UUID of the task to update. **Required.**
- (All arguments from `add_task` are available except `--task_creator`)
- `--status` (enum): `Open`|`InProgress`|`Done`|`Archived`|`Gutter`.
- `--is_milestone` (bool): `true` | `false`.
- `--is_subtask` (bool): `true` | `false`.

---

### `delete_task`
Deletes a task.

- `--task_id` (str): UUID of the task. **Required.**
- `--actor` (str): Who is performing the action.

---

### `show_task`
Displays the full details of a single task.

- `--task_id` (str): UUID of the task. **Required.**

---

### `list_tasks`
Lists tasks with powerful filtering and sorting.

- `--sort_by` (enum): `priority`|`criticality`|`urgency`|`enthusiasm`|`due_date`|`order`.
- `--limit` (int): Number of tasks to return.
- `--ranked-view`: Use the default complex ranking algorithm.
- `--status_filter` (list): Space-separated list of statuses to include.
- `--tags_filter` (list): Space-separated list of tags to filter by.
- `--tags_mode` (enum): `any` (match any tag) | `all` (must match all tags).
- `--search` (str): Keyword search across title and description.
- `--creator_filter` (str): Filter by `task_creator`.
- `--parent_task_id_filter` (str): Get subtasks for a given parent.
- `--is_subtask_filter` (bool): `true` | `false`.
- `--format` (enum): `text` | `json`.
- `--include_done`: Include tasks with `Done` status.
- `--include_archived`: Include tasks with `Archived` status.

---

### `set_wip_limit`
Sets a Work-In-Progress limit for a status column.

- `--status` (enum): The status column (e.g., `InProgress`). **Required.**
- `--limit` (int): Max number of tasks allowed. `0` removes the limit. **Required.**

---

### `get_wip_limits`
Displays current WIP limits. (No arguments)

---

### `report`
Generates a metrics report of the board. (No arguments)
