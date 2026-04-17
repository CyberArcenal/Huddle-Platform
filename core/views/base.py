from django.http import JsonResponse
from django.db import connections
from django.db.utils import OperationalError

def health_check(request):
    db_status = "ok"
    try:
        connections['default'].cursor()
    except OperationalError:
        db_status = "error"

    return JsonResponse({
        "status": "ok" if db_status == "ok" else "error",
        "database": db_status,
        "version": "1.0.0"
    })