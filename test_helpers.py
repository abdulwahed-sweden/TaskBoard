
import random
import string
import uuid

from datetime import timedelta, time
from django.contrib.auth.models import User
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from datetime import datetime

from tasks import models as tasks_models
from organizations import models as organizations_models


def random_string(length=10):
    # Create a random string of length length
    letters = string.ascii_lowercase
    return "".join(random.choice(letters) for i in range(length))


def create_User(**kwargs):
    defaults = {
        "username": "%s_username" % random_string(5),
        "email": "%s_username@tempurl.com" % random_string(5),
    }
    defaults.update(**kwargs)
    return User.objects.create(**defaults)


def create_AbstractUser(**kwargs):
    defaults = {
        "username": "%s_username" % random_string(5),
        "email": "%s_username@tempurl.com" % random_string(5),
    }
    defaults.update(**kwargs)
    return AbstractUser.objects.create(**defaults)


def create_AbstractBaseUser(**kwargs):
    defaults = {
        "username": "%s_username" % random_string(5),
        "email": "%s_username@tempurl.com" % random_string(5),
    }
    defaults.update(**kwargs)
    return AbstractBaseUser.objects.create(**defaults)


def create_Group(**kwargs):
    defaults = {
        "name": "%s_group" % random_string(5),
    }
    defaults.update(**kwargs)
    return Group.objects.create(**defaults)


def create_ContentType(**kwargs):
    defaults = {
    }
    defaults.update(**kwargs)
    return ContentType.objects.create(**defaults)


_UNSET = object()


def create_tasks_Task(**kwargs):
    # Resolve owner: default to a fresh user, but allow an explicit None.
    owner = kwargs.pop("owner", _UNSET)
    if owner is _UNSET:
        owner = create_User()
    # Every task now lives in a project. When none is given, create one and
    # (for a real owner) make them a member so the task is visible under the
    # org-membership scoping introduced in Phase 2.
    project = kwargs.pop("project", None)
    if project is None:
        project = create_organizations_Project()
        if owner is not None:
            create_organizations_Membership(
                user=owner,
                organization=project.organization,
                role=organizations_models.Membership.Role.MEMBER,
            )
    defaults = {
        'created': '2022-01-01:09:00:00',
        'last_updated': '2022-01-01:09:00:00',
        'title': 'text',
        'notes': 'some\ntext',
        'is_done': True,
        'due_date': '2022-01-01',
    }
    defaults.update(**kwargs)
    defaults["owner"] = owner
    defaults["project"] = project
    return tasks_models.Task.objects.create(**defaults)


def create_organizations_Organization(**kwargs):
    name = kwargs.pop("name", "%s Org" % random_string(5))
    defaults = {
        "name": name,
        "slug": "%s-org" % random_string(8),
    }
    defaults.update(**kwargs)
    return organizations_models.Organization.objects.create(**defaults)


def create_organizations_Membership(**kwargs):
    defaults = {
        "role": organizations_models.Membership.Role.MEMBER,
    }
    defaults.update(**kwargs)
    defaults.setdefault("user", create_User())
    defaults.setdefault("organization", create_organizations_Organization())
    return organizations_models.Membership.objects.create(**defaults)


def create_organizations_Project(**kwargs):
    defaults = {
        "name": "%s Project" % random_string(5),
    }
    defaults.update(**kwargs)
    defaults.setdefault("organization", create_organizations_Organization())
    return organizations_models.Project.objects.create(**defaults)


def create_organizations_ProjectType(**kwargs):
    defaults = {
        "name": "%s Type" % random_string(5),
    }
    defaults.update(**kwargs)
    return organizations_models.ProjectType.objects.create(**defaults)


def create_organizations_FieldDefinition(**kwargs):
    defaults = {
        "name": "field_%s" % random_string(4),
        "label": "Field",
        "field_type": organizations_models.FieldDefinition.FieldType.TEXT,
        "required": False,
    }
    defaults.update(**kwargs)
    defaults.setdefault("project_type", create_organizations_ProjectType())
    return organizations_models.FieldDefinition.objects.create(**defaults)


def create_organizations_StatusDefinition(**kwargs):
    name = kwargs.pop("name", "status_%s" % random_string(4))
    defaults = {
        "name": name,
        "label": name.replace("_", " ").title(),
        "order": 0,
        "is_default": False,
        "is_terminal": False,
    }
    defaults.update(**kwargs)
    defaults.setdefault("project_type", create_organizations_ProjectType())
    return organizations_models.StatusDefinition.objects.create(**defaults)


def create_tasks_Comment(**kwargs):
    defaults = {
        "body": "a comment",
    }
    defaults.update(**kwargs)
    defaults.setdefault("task", create_tasks_Task())
    defaults.setdefault("author", create_User())
    return tasks_models.Comment.objects.create(**defaults)

  
