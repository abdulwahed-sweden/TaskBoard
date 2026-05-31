
import pytest
import test_helpers
from django.urls import reverse

pytestmark = [pytest.mark.django_db]


def tests_Task_list_view(client):
    user = test_helpers.create_User()
    client.force_login(user)
    instance1 = test_helpers.create_tasks_Task(owner=user)
    instance2 = test_helpers.create_tasks_Task(owner=user)
    url = reverse("tasks:Task_list")
    response = client.get(url)
    assert response.status_code == 200
    assert str(instance1) in response.content.decode("utf-8")
    assert str(instance2) in response.content.decode("utf-8")


def tests_Task_list_view_requires_login(client):
    url = reverse("tasks:Task_list")
    response = client.get(url)
    assert response.status_code == 302
    assert reverse("login") in response.url


def tests_Task_list_view_only_shows_own_tasks(client):
    user = test_helpers.create_User()
    other = test_helpers.create_User()
    client.force_login(user)
    mine = test_helpers.create_tasks_Task(owner=user, title="mine")
    theirs = test_helpers.create_tasks_Task(owner=other, title="theirs")
    response = client.get(reverse("tasks:Task_list"))
    body = response.content.decode("utf-8")
    assert str(mine) in body
    assert str(theirs) not in body


def tests_Task_create_view(client):
    user = test_helpers.create_User()
    client.force_login(user)
    url = reverse("tasks:Task_create")
    data = {
      'title': 'text',
      'notes': 'some\ntext',
      'is_done': True,
      'due_date': '2022-01-01',
    }
    response = client.post(url, data)
    assert response.status_code == 302


def tests_Task_create_view_assigns_owner(client):
    from tasks.models import Task

    user = test_helpers.create_User()
    client.force_login(user)
    url = reverse("tasks:Task_create")
    data = {
      'title': 'ownerless-post',
      'notes': 'some\ntext',
      'is_done': True,
      'due_date': '2022-01-01',
    }
    response = client.post(url, data)
    assert response.status_code == 302
    task = Task.objects.get(title='ownerless-post')
    assert task.owner == user


def tests_Task_detail_view(client):
    user = test_helpers.create_User()
    client.force_login(user)
    instance = test_helpers.create_tasks_Task(owner=user)
    url = reverse("tasks:Task_detail", args=[instance.pk, ])
    response = client.get(url)
    assert response.status_code == 200
    assert str(instance) in response.content.decode("utf-8")


def tests_Task_detail_view_other_owner_404(client):
    user = test_helpers.create_User()
    other = test_helpers.create_User()
    client.force_login(user)
    instance = test_helpers.create_tasks_Task(owner=other)
    url = reverse("tasks:Task_detail", args=[instance.pk, ])
    response = client.get(url)
    assert response.status_code == 404


def tests_Task_update_view(client):
    user = test_helpers.create_User()
    client.force_login(user)
    instance = test_helpers.create_tasks_Task(owner=user)
    url = reverse("tasks:Task_update", args=[instance.pk, ])
    data = {
      'title': 'text',
      'notes': 'some\ntext',
      'is_done': True,
      'due_date': '2022-01-01',
    }
    response = client.post(url, data)
    assert response.status_code == 302


def tests_signup_view_creates_user(client):
    from django.contrib.auth.models import User

    url = reverse("signup")
    assert client.get(url).status_code == 200
    response = client.post(url, {
        "username": "newcomer",
        "password1": "sup3r-secret-pw",
        "password2": "sup3r-secret-pw",
    })
    assert response.status_code == 302
    assert User.objects.filter(username="newcomer").exists()


def tests_profile_view_requires_login(client):
    response = client.get(reverse("profile"))
    assert response.status_code == 302
    assert reverse("login") in response.url


def tests_profile_view_shows_own_tasks(client):
    user = test_helpers.create_User()
    client.force_login(user)
    task = test_helpers.create_tasks_Task(owner=user, title="profile-task")
    response = client.get(reverse("profile"))
    assert response.status_code == 200
    assert "profile-task" in response.content.decode("utf-8")


def tests_password_reset_sends_email(client, mailoutbox):
    user = test_helpers.create_User(email="resetme@example.com")
    assert client.get(reverse("password_reset")).status_code == 200
    response = client.post(reverse("password_reset"), {"email": user.email})
    assert response.status_code == 302
    assert response.url == reverse("password_reset_done")
    assert len(mailoutbox) == 1
    email = mailoutbox[0]
    assert email.subject == "Reset your TaskBoard password"
    assert user.email in email.to
    assert "choose a new password" in email.body


def tests_password_reset_unknown_email_sends_nothing(client, mailoutbox):
    response = client.post(reverse("password_reset"), {"email": "nobody@example.com"})
    assert response.status_code == 302
    assert len(mailoutbox) == 0


def tests_change_password_updates_credentials(client):
    user = test_helpers.create_User()
    user.set_password("original-pw-123")
    user.save()
    client.force_login(user)
    assert client.get(reverse("password_change")).status_code == 200
    response = client.post(reverse("password_change"), {
        "old_password": "original-pw-123",
        "new_password1": "brand-new-pw-456",
        "new_password2": "brand-new-pw-456",
    })
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("brand-new-pw-456")
