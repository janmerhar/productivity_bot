from shutil import register_unpack_format
from ticktick.oauth2 import OAuth2        # OAuth2 Manager
from ticktick.api import TickTickClient   # Main Interface


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
    - get_completed(self, start, end=None, full=True, tz=None)
    - get_from_project(self, project)
    - make_subtask(self, obj, parent)
    - move(self, obj, new)
    - move_all(self, old, new)
    - update(self, task)
    """

    def completeTask(self, task_title):
        task = self.client.get_by_fields(title=task_title, search="tasks")
        if task == []:
            return None

        completed_task = self.client.task.complete(task)
        return completed_task

    def deleteTask(self, task_title):
        task = self.client.get_by_fields(title=task_title, search="tasks")
        if task == []:
            return None

        completed_task = self.client.task.delete(task)
        return completed_task
    #
    # Projects
    # https://lazeroffmichael.github.io/ticktick-py/usage/projects/
    #

    """
    - create(self, name, color='random', project_type='TASK', folder_id=None) 
    - create_folder(self, name)
    - delete(self, ids)
    - delete_folder(self, ids)
    - update(self, obj) 
    - update_folder(self, obj) 
    """

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

    ticktick = TickTickFunctions(
        env["TICK_EMAIL"], env["TICK_PASSWORD"], env["TICK_ID"], env["TICK_SECRET"], env["TICK_URI"])

    # res = ticktick.completeTask("test task")
    res = ticktick.deleteTask("test task")
    print(res)
