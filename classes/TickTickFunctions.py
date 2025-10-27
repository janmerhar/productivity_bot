from ticktick.oauth2 import OAuth2
from ticktick.api import TickTickClient

from abstract.FunctionsAbstract import FunctionsAbstract

from config.env import env
from config.db import mongo_db


class TickTickFunctions(FunctionsAbstract):
    def __init__(self, email, password, client_id, client_secret, uri):
        auth_client = OAuth2(
            client_id=client_id, client_secret=client_secret, redirect_uri=uri
        )

        self.client = TickTickClient(email, password, auth_client)

        self.mongo_commands = mongo_db["custom_commands"]
        self.mongo_aliases = mongo_db["aliases"]

    #
    # Tasks
    # https://lazeroffmichael.github.io/ticktick-py/usage/tasks/
    #

    """
    - builder(self, ...)
    - dates(self, start, due=None, tz=None)
    - move_all(self, old, new)
    """

    def getTaskByTitle(self, title):
        project = self.client.get_by_fields(search="tasks", title=title)
        return project

    def getTaskById(self, task_id):
        project = self.client.get_by_id(search="tasks", obj_id=task_id)
        return project

    def getTask(self, identifier):
        by_name = self.getTaskByTitle(identifier)
        if by_name == [] or by_name == {}:
            by_id = self.getTaskById(identifier)

            if by_id == [] or by_id == {}:
                return None
            else:
                return by_id
        else:
            return by_name

    def createTask(
        self,
        title,
        projectId=None,
        content=None,
        desc=None,
        allDay=None,
        startDate=None,
        dueDate=None,
        timeZone=None,
        reminders=None,
        repeat=None,
        priority=None,
        sortOrder=None,
        items=None,
    ):
        task = self.client.task.builder(
            title,
            projectId=projectId,
            content=content,
            desc=desc,
            allDay=allDay,
            startDate=startDate,
            dueDate=dueDate,
            timeZone=timeZone,
            reminders=reminders,
            repeat=repeat,
            priority=priority,
            sortOrder=sortOrder,
            items=items,
        )
        newTask = self.client.task.create(task)
        return newTask

    def createSubtask(self, task, parent):
        subtask = self.client.task.make_subtask(task, parent)

        return subtask

    def completeTask(self, task_title):
        task = self.client.get_by_fields(title=task_title, search="tasks")
        if task == []:
            return None

        completed_task = self.client.task.complete(task)
        return completed_task

    def updateTask(self, task):
        updatedTask = self.client.task.update(task)
        return updatedTask

    def moveTask(self, task, new_project):
        new_task = self.client.task.move(task, new_project)

        return new_task

    def deleteTask(self, task_title):
        task = self.client.get_by_fields(title=task_title, search="tasks")
        if task == []:
            return None

        completed_task = self.client.task.delete(task)
        return completed_task

    def tasksFromProject(self, project_name):
        project = self.getProjectByName(project_name)

        if project == []:
            return None

        tasks = self.client.task.get_from_project(project["id"])
        return tasks

    #
    # Projects
    # https://lazeroffmichael.github.io/ticktick-py/usage/projects/
    #

    """
    - create_folder(self, name)
    - delete(self, ids)
    - update_folder(self, obj)
    """

    """
    This method wants included emoji with name
    - e.g. 🚧Projekti
    """

    def getProjects(self):
        pass

    def getProjectByName(self, name):
        project = self.client.get_by_fields(search="projects", name=name)
        return project

    def getProjectById(self, project_id):
        project = self.client.get_by_id(search="projects", obj_id=project_id)
        return project

    def getProject(self, identifier):
        by_name = self.getProjectByName(identifier)
        if by_name == []:
            by_id = self.getProjectById(identifier)

            if by_id == []:
                return None
            else:
                return by_id
        else:
            return by_name

    """
    Modify search to search by non-existent,
    using self.getProject()
    """

    def createProject(self, name, color="random", project_type="TASK", folder_id=None):
        search = self.getProjectByName(name)

        if search != []:
            return None
        else:
            project = self.client.project.create(
                name=name, color=color, project_type=project_type, folder_id=folder_id
            )

            return project

    def updateProject(
        self, identifier, name=None, color=None, project_type=None, folder_id=None
    ):
        project = self.getProject(identifier)

        if project == {}:
            return None

        if (
            name is None
            and color is None
            and project_type is None
            and folder_id is None
        ):
            return project

        if name is not None:
            project["name"] = name
        if color is not None:
            project["color"] = color
        if project_type is not None:
            project["project_type"] = project_type
        if folder_id is not None:
            project["folder_id"] = folder_id

        updatedProject = self.client.project.update(project)

        return updatedProject

    def deleteProject(self, name):
        search = self.getProject(name)

        if search == {}:
            return None

        deletedProject = self.client.project.delete(search["id"])

        return deletedProject

    #
    # Tags
    # https://lazeroffmichael.github.io/ticktick-py/usage/tags/
    #

    """
    - color(self, label, color)
    - create(self, label, color='random', parent=None, sort=None)
    - delete(self, label)
    - merge(self, label, merged)
    - nesting(self, child, parent)
    - rename(self, old, new)
    - sorting(self, label, sort)
    - update(self, obj)
    -
    """

    #
    # Helpers
    # https://lazeroffmichael.github.io/ticktick-py/usage/helpers/
    #

    #
    # Aliases
    #

    def parseShortcutArguments(self, arguments: str) -> dict[str, str]:
        param = {}

        arg_lines = arguments.split(";")

        for arg_line in arg_lines:
            arg_line = arg_line.strip()
            command = arg_line.split(" ")[0].strip()

            if len(command) > 0:
                param[command] = " ".join(arg_line.split(" ")[1:]).strip()

        return param

    def saveShortcut2(self, command: str, alias: str, param: object = {}) -> dict:
        data = {
            "alias": alias,  # Name of the shortened command
            "command": command,  # Name of the slash command
            "application": "ticktick",
            "number_of_runs": 0,
            "param": param,  # Parameters passed to aliased slash command
        }

        res = self.mongo_aliases.insert_one(data)

        return data


if __name__ == "__main__":
    from config.env import env
    import json

    ticktick = TickTickFunctions(
        env["TICK_EMAIL"],
        env["TICK_PASSWORD"],
        env["TICK_ID"],
        env["TICK_SECRET"],
        env["TICK_URI"],
    )

    # res = ticktick.completeTask("test task")
    # res = ticktick.deleteTask("test task")
    # res = ticktick.tasksFromProject("🍔Hrana")
    # res = ticktick.tasksFromProject("🍔Hrana")
    # res = ticktick.createProject(name="Discord")
    # res = ticktick.deleteProject(name="Prazen list iz discorda69420")
    # res = ticktick.getProjectByName("🚧Projekti")
    # res = ticktick.getProjectById("613930938f08ae2c444a64a7")
    # res = ticktick.createSubtask(ticktick.createTask(
    # title="Child task"), ticktick.createTask(title="Parent task")["id"],)
    # res = ticktick.moveTask(ticktick.createTask(
    # title="Premakni v Projekti"), "613930938f08ae2c444a64a7")
    # res = ticktick.getProject("613930938f08ae2c444a64a7")
    # res = ticktick.updateProject(identifier="Discord renamed", name="Discord")
    # res = ticktick.getTaskByTitle("discord task")
    # res = ticktick.getTaskById("78644c2cb7c51ec7c1ca5bb1")
    res = ticktick.getTask("discord task")
    print(res)
    # print(json.dumps(res, indent=2))
