from django.db import models


class Stack(models.Model):
    STACK_CHOICES = [
        ('Fullstack', 'Fullstack'),
        ('Backend', 'Backend'),
        ('Frontend', 'Frontend'),
    ]

    name = models.CharField(max_length=100, choices=STACK_CHOICES, unique=True)

    def __str__(self):
        return self.name


class Level(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class ProgLanguage(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name
