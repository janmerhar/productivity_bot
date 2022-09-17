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
    - complete(self, task)
    - dates(self, start, due=None, tz=None)
    - delete(self, task)
    - get_completed(self, start, end=None, full=True, tz=None)
    - get_from_project(self, project)
    - make_subtask(self, obj, parent)
    - move(self, obj, new)
    - move_all(self, old, new)
    - update(self, task)
    """

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
    ticktick = TickTickFunctions(
        email, password, client_id, client_secret, uri)
