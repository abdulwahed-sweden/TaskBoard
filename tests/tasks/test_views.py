
import uuid
import pytest
import test_helpers
from datetime import timedelta, time
from django.urls import reverse

pytestmark = [pytest.mark.django_db]


def tests_Task_list_view(client):
    instance1 = test_helpers.create_tasks_Task()
    instance2 = test_helpers.create_tasks_Task()
    url = reverse("tasks:Task_list")
    response = client.get(url)
    assert response.status_code == 200
    assert str(instance1) in response.content.decode("utf-8")
    assert str(instance2) in response.content.decode("utf-8")


def tests_Task_create_view(client):
    url = reverse("tasks:Task_create")
    data = {
      'created': '2022-01-01:09:00:00',
      'last_updated': '2022-01-01:09:00:00',
      'title': 'text',
      'notes': 'some\ntext',
      'is_done': True,
      'due_date': '2022-01-01',
      "owner": test_helpers.create_User().pk,
    }
    response = client.post(url, data)
    assert response.status_code == 302


def tests_Task_create_view_without_owner(client):
    from tasks.models import Task

    url = reverse("tasks:Task_create")
    data = {
      'title': 'ownerless',
      'notes': 'some\ntext',
      'is_done': True,
      'due_date': '2022-01-01',
    }
    response = client.post(url, data)
    assert response.status_code == 302
    task = Task.objects.get(title='ownerless')
    assert task.owner is None


def tests_Task_detail_view(client):
    instance = test_helpers.create_tasks_Task()
    url = reverse("tasks:Task_detail", args=[instance.pk, ])
    response = client.get(url)
    assert response.status_code == 200
    assert str(instance) in response.content.decode("utf-8")

    
def tests_Task_update_view(client):
    instance = test_helpers.create_tasks_Task()
    url = reverse("tasks:Task_update", args=[instance.pk, ])
    data = {
      'created': '2022-01-01:09:00:00',
      'last_updated': '2022-01-01:09:00:00',
      'title': 'text',
      'notes': 'some\ntext',
      'is_done': True,
      'due_date': '2022-01-01',
      "owner": test_helpers.create_User().pk,
    }
    response = client.post(url, data)
    assert response.status_code == 302
