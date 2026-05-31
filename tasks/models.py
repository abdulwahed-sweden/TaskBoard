from django.db import models
from django.urls import reverse


class Task(models.Model):

    owner = models.ForeignKey("auth.User", null=True, on_delete=models.CASCADE)

    # Fields
    created = models.DateTimeField(auto_now_add=True, editable=False)
    last_updated = models.DateTimeField(auto_now=True, editable=False)
    title = models.CharField(max_length=120)
    notes = models.TextField(blank=True, default='')
    is_done = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.title

    @staticmethod
    def get_create_url():
        return reverse("tasks:Task_create")

    def get_absolute_url(self):
        return reverse("tasks:Task_detail", args=(self.pk,))

    def get_update_url(self):
        return reverse("tasks:Task_update", args=(self.pk,))

    def get_delete_url(self):
        return reverse("tasks:Task_delete", args=(self.pk,))



