from ticktick.oauth2 import OAuth2        # OAuth2 Manager
from ticktick.api import TickTickClient   # Main Interface
import datetime


class TickTickFunctions:
    def __init__(self, email, password, client_id, client_secret, uri):
        self.auth_client = OAuth2(client_id=client_id,
                                  client_secret=client_secret,
                                  redirect_uri=uri)

        self.client = TickTickClient(email, password, self.auth_client)

    #
    # Tasks
    # https://lazeroffmichael.github.io/ticktick-py/usage/tasks/
    #

    """
    - builder(self, ...)
    - dates(self, start, due=None, tz=None)
    - move_all(self, old, new)
    """

    def createTask(self, title, projectId=None, content=None, desc=None, allDay=None, startDate=None, dueDate=None, timeZone=None, reminders=None, repeat=None, priority=None, sortOrder=None, items=None):
        task = self.client.task.builder(title, projectId=projectId, content=content, desc=desc, allDay=allDay, startDate=startDate,
                                        dueDate=dueDate, timeZone=timeZone, reminders=reminders, repeat=repeat, priority=priority, sortOrder=sortOrder, items=items)
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

    def getProjectByName(self, name):
        project = self.client.get_by_fields(
            search="projects", name=name)
        return project

    def getProjectById(self, project_id):
        project = self.client.get_by_id(
            search="projects", obj_id=project_id)
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

    def createProject(self, name, color='random', project_type='TASK', folder_id=None):
        search = self.getProjectByName(name)

        if search == []:
            None

        project = self.client.project.create(
            name=name, color=color, project_type=project_type, folder_id=folder_id)

        return project

    def updateProject(self, project):
        updatedProject = self.client.project.update(project)

        return updatedProject

    def deleteProject(self, project_id):
        deletedProject = self.client.project.delete(project_id)

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


if __name__ == '__main__':
    from dotenv import dotenv_values
    env = dotenv_values(".env")
    import json

    ticktick = TickTickFunctions(
        env["TICK_EMAIL"], env["TICK_PASSWORD"], env["TICK_ID"], env["TICK_SECRET"], env["TICK_URI"])

    # res = ticktick.completeTask("test task")
    # res = ticktick.deleteTask("test task")
    # res = ticktick.tasksFromProject("🍔Hrana")
    # res = ticktick.tasksFromProject("🍔Hrana")
    # res = ticktick.createProject(name="projekt")
    # res = ticktick.getProjectByName("🚧Projekti")
    # res = ticktick.getProjectById("613930938f08ae2c444a64a7")
    # res = ticktick.createSubtask(ticktick.createTask(
    # title="Child task"), ticktick.createTask(title="Parent task")["id"],)
    # res = ticktick.moveTask(ticktick.createTask(
    # title="Premakni v Projekti"), "613930938f08ae2c444a64a7")
    res = ticktick.getProject("613930938f08ae2c444a64a7")
    # print(res)
    print(json.dumps(res, indent=2))
