import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledgerflow.settings.development")

app = Celery("ledgerflow")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    pass


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
